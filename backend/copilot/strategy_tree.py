"""策略树数据结构、embedding 预计算与节点匹配。"""
import json
import logging
import numpy as np
from typing import Any

from backend.llm_provider import get_embedding

logger = logging.getLogger("uvicorn")


class StrategyTreeNavigator:
    """在预计算的策略树上做 embedding 匹配导航。"""

    def __init__(self, tree: dict):
        self.tree = tree
        self.nodes: dict = tree.get("nodes", {})
        self.root_nodes: list[str] = tree.get("root_nodes", [])
        self._embeddings: dict[str, list[tuple[str, list[float]]]] = {}
        self._current_position: str | None = None

    async def precompute_embeddings(self):
        """预计算所有节点 sample_questions 的 embedding。"""
        embed_model = get_embedding()
        for node_id, node in self.nodes.items():
            questions = node.get("sample_questions", [])
            if not questions:
                continue
            node_embs = []
            for q in questions:
                try:
                    emb = embed_model.get_text_embedding(q)
                    node_embs.append((q, emb))
                except Exception as e:
                    logger.warning(f"Failed to embed question '{q[:30]}...': {e}")
            self._embeddings[node_id] = node_embs
        logger.info(f"Precomputed embeddings for {len(self._embeddings)} strategy tree nodes")

    def match_utterance(self, utterance_embedding: list[float], threshold: float = 0.45) -> tuple[str | None, str | None, float]:
        """匹配 utterance 到最相似的策略树节点。

        Returns: (node_id, intent, similarity_score)
        """
        best_score = -1.0
        best_node_id = None
        utt_vec = np.array(utterance_embedding, dtype=np.float32)
        utt_norm = np.linalg.norm(utt_vec)
        if utt_norm == 0:
            return None, None, 0.0

        for node_id, embs in self._embeddings.items():
            for _, emb in embs:
                emb_vec = np.array(emb, dtype=np.float32)
                emb_norm = np.linalg.norm(emb_vec)
                if emb_norm == 0:
                    continue
                score = float(np.dot(utt_vec, emb_vec) / (utt_norm * emb_norm))
                if score > best_score:
                    best_score = score
                    best_node_id = node_id

        if best_score < threshold or best_node_id is None:
            return None, None, best_score

        node = self.nodes[best_node_id]
        self._current_position = best_node_id
        return best_node_id, node.get("intent", "unknown"), best_score

    def get_children(self, node_id: str) -> list[dict]:
        """获取节点的子节点（追问方向）。"""
        node = self.nodes.get(node_id)
        if not node:
            return []
        return [
            self.nodes[cid]
            for cid in node.get("children", [])
            if cid in self.nodes
        ]

    def get_node(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    @property
    def current_position(self) -> str | None:
        return self._current_position


def parse_strategy_tree(raw_json: str) -> dict:
    """从 LLM 输出解析策略树 JSON。"""
    try:
        text = raw_json.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse strategy tree JSON: {raw_json[:200]}")
        return {"root_nodes": [], "nodes": {}, "phase_order": []}
