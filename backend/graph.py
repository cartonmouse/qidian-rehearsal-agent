"""题目关联图谱 — 从历史 drill 题目构建语义相似度图。"""
import hashlib
import json
import sqlite3
from datetime import datetime

import numpy as np

from backend.config import settings
from backend.vector_memory import _embed, _serialize, _deserialize, _cosine_similarity

DB_PATH = settings.db_path
SIMILARITY_THRESHOLD = 0.65


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


_QUESTION_EMB_DDL = """
    CREATE TABLE IF NOT EXISTS question_embeddings (
        question_hash TEXT,
        topic         TEXT,
        question_text TEXT,
        embedding     BLOB NOT NULL,
        user_id       TEXT,
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (question_hash, user_id)
    )
"""


def _init_question_embeddings_table(conn: sqlite3.Connection):
    conn.execute(_QUESTION_EMB_DDL)
    # Migrate legacy single-column PK (question_hash) → composite (question_hash, user_id).
    # The table is a recomputable cache, so dropping it on migration is harmless.
    pk_cols = [r["name"] for r in conn.execute("PRAGMA table_info(question_embeddings)") if r["pk"]]
    if pk_cols == ["question_hash"]:
        conn.execute("DROP TABLE question_embeddings")
        conn.execute(_QUESTION_EMB_DDL)
    conn.commit()


def _hash_question(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def clear_user_question_embeddings(user_id: str):
    """Drop a user's cached question embeddings (called on embedding model change)."""
    conn = _get_conn()
    _init_question_embeddings_table(conn)
    conn.execute("DELETE FROM question_embeddings WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def _extract_questions(conn: sqlite3.Connection, topic: str, user_id: str) -> list[dict]:
    """Extract all questions with scores from completed drill sessions for a topic."""
    rows = conn.execute(
        "SELECT session_id, questions, scores, created_at FROM sessions "
        "WHERE topic = ? AND user_id = ? AND mode = 'topic_drill' AND review IS NOT NULL "
        "ORDER BY created_at ASC",
        (topic, user_id),
    ).fetchall()

    # question_text → aggregated record, latest occurrence wins for current display fields
    seen: dict[str, dict] = {}
    for row in rows:
        questions = json.loads(row["questions"] or "[]")
        scores = json.loads(row["scores"] or "[]")
        score_map = {s["question_id"]: s for s in scores if "question_id" in s}

        for q in questions:
            text = q.get("question", "").strip()
            if not text:
                continue
            qid = q.get("id")
            sc = score_map.get(qid, {})
            score_val = sc.get("score")
            # Only include questions that were actually answered and scored
            if not isinstance(score_val, (int, float)):
                continue

            existing = seen.get(text)
            if existing:
                existing["attempts"] += 1
                existing["score_sum"] += score_val
                existing["best_score"] = max(existing["best_score"], score_val)
                existing["score"] = score_val
                existing["focus_area"] = q.get("focus_area", "") or existing["focus_area"]
                existing["difficulty"] = q.get("difficulty", 3)
                existing["date"] = row["created_at"][:10] if row["created_at"] else ""
                existing["session_id"] = row["session_id"]
                continue

            seen[text] = {
                "question": text,
                "score": score_val,
                "score_sum": score_val,
                "best_score": score_val,
                "attempts": 1,
                "focus_area": q.get("focus_area", ""),
                "difficulty": q.get("difficulty", 3),
                "date": row["created_at"][:10] if row["created_at"] else "",
                "session_id": row["session_id"],
            }

    for item in seen.values():
        item["avg_score"] = round(item["score_sum"] / item["attempts"], 1)
        item.pop("score_sum", None)

    return list(seen.values())


def _get_or_compute_embeddings(
    conn: sqlite3.Connection,
    questions: list[dict],
    topic: str,
    user_id: str,
) -> np.ndarray:
    """Return (N, D) embedding matrix. Uses cache table, computes missing.

    Cache is scoped per user — vectors from different users' embedding models have
    incompatible dimensions and must never be mixed in one matrix."""
    _init_question_embeddings_table(conn)

    hashes = [_hash_question(q["question"]) for q in questions]

    # Load cached (this user only)
    cached: dict[str, np.ndarray] = {}
    if hashes:
        placeholders = ",".join("?" for _ in hashes)
        rows = conn.execute(
            f"SELECT question_hash, embedding FROM question_embeddings "
            f"WHERE user_id = ? AND question_hash IN ({placeholders})",
            [user_id, *hashes],
        ).fetchall()
        for r in rows:
            cached[r["question_hash"]] = _deserialize(r["embedding"])

    # Find missing
    to_embed = []
    to_embed_idx = []
    for i, (h, q) in enumerate(zip(hashes, questions)):
        if h not in cached:
            to_embed.append(q["question"])
            to_embed_idx.append(i)

    # Batch embed missing
    if to_embed:
        from backend.llm_provider import get_embedding
        embed_model = get_embedding(user_id)
        vectors = embed_model.get_text_embedding_batch(to_embed)
        now = datetime.now().isoformat()
        for text, vec, idx in zip(to_embed, vectors, to_embed_idx):
            vec_np = np.array(vec, dtype=np.float32)
            h = hashes[idx]
            cached[h] = vec_np
            conn.execute(
                "INSERT OR REPLACE INTO question_embeddings (question_hash, topic, question_text, embedding, created_at, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (h, topic, text, _serialize(vec_np), now, user_id),
            )
        conn.commit()

    # Build matrix in order
    matrix = np.stack([cached[h] for h in hashes])
    return matrix


def build_graph(topic: str, user_id: str) -> dict:
    """Build question relationship graph for a topic.

    Returns {"nodes": [...], "links": [...]}
    """
    conn = _get_conn()
    questions = _extract_questions(conn, topic, user_id)

    if len(questions) < 2:
        conn.close()
        return {
            "nodes": [
                {"id": i, **q} for i, q in enumerate(questions)
            ],
            "links": [],
        }

    embeddings = _get_or_compute_embeddings(conn, questions, topic, user_id)
    conn.close()

    # Build nodes
    nodes = []
    for i, q in enumerate(questions):
        nodes.append({
            "id": i,
            "question": q["question"],
            "score": q["score"],
            "avg_score": q.get("avg_score", q["score"]),
            "best_score": q.get("best_score", q["score"]),
            "attempts": q.get("attempts", 1),
            "focus_area": q["focus_area"],
            "difficulty": q["difficulty"],
            "date": q["date"],
            "session_id": q.get("session_id"),
        })

    # Compute pairwise similarity → links
    links = []
    n = len(questions)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(_cosine_similarity(embeddings[i], embeddings[j].reshape(1, -1))[0])
            if sim >= SIMILARITY_THRESHOLD:
                links.append({
                    "source": i,
                    "target": j,
                    "similarity": round(sim, 3),
                })

    return {"nodes": nodes, "links": links}
