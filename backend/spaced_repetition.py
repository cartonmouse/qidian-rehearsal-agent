"""间隔重复系统 — SM-2 算法。

为每个薄弱点维护复习调度：
- 答对了 → 间隔拉长（1天 → 3天 → 7天 → ...）
- 答错了 → 间隔重置到 1 天
- 每次出题时优先出"到期需要复习"的知识点
"""
from datetime import date, timedelta

from backend.memory import _load_profile, _save_profile


def sm2_update(sr_state: dict, score_0_10: float) -> dict:
    """SM-2 algorithm update.

    Args:
        sr_state: Current spaced repetition state {interval_days, ease_factor, repetitions, ...}
        score_0_10: Score on 0-10 scale (mapped to SM-2 quality 0-5)

    Returns:
        Updated SR state dict
    """
    # Map 0-10 to SM-2 quality 0-5 (pass threshold at 5/10)
    if score_0_10 <= 2:
        quality = 0
    elif score_0_10 <= 4:
        quality = 2
    elif score_0_10 <= 5:
        quality = 3
    elif score_0_10 <= 7:
        quality = 4
    else:
        quality = 5
    ef = sr_state.get("ease_factor", 2.5)
    reps = sr_state.get("repetitions", 0)

    if quality >= 3:  # Pass
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 3
        else:
            interval = int(sr_state.get("interval_days", 1) * ef)
        reps += 1
    else:  # Fail — reset
        interval = 1
        reps = 0

    # Update ease factor (never below 1.3)
    ef = max(1.3, ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

    return {
        "interval_days": interval,
        "ease_factor": round(ef, 2),
        "repetitions": reps,
        "next_review": (date.today() + timedelta(days=interval)).isoformat(),
        "last_score": score_0_10,
    }


def get_due_reviews(user_id: str, topic: str = None) -> list[dict]:
    """Get weak points that are due for review.

    Returns list of weak_point dicts sorted by ease_factor (hardest first).
    """
    profile = _load_profile(user_id)
    today = date.today().isoformat()
    due = []

    for wp in profile.get("weak_points", []):
        if wp.get("improved") or wp.get("archived"):
            continue
        # 跨领域规律不是可复习的知识点;老数据的表现轴条目同样排除
        if wp.get("source") == "consolidated" or wp.get("axis") == "performance":
            continue
        if topic and wp.get("topic") != topic:
            continue
        sr = wp.get("sr", {})
        next_review = sr.get("next_review", "2000-01-01")
        if next_review <= today:
            due.append(wp)

    # Hardest first (lowest ease_factor)
    due.sort(key=lambda x: x.get("sr", {}).get("ease_factor", 2.5))
    return due


def update_weak_point_sr(topic: str, point_text: str, score: float, user_id: str):
    """Update spaced repetition state for a specific weak point after evaluation.

    Matches by topic + embedding similarity.
    """
    from backend.vector_memory import find_similar_weak_point

    profile = _load_profile(user_id)

    # Filter candidates by topic
    candidates = [
        (i, wp) for i, wp in enumerate(profile.get("weak_points", []))
        if not wp.get("improved") and not wp.get("archived")
        and (not topic or wp.get("topic") == topic)
    ]
    if not candidates:
        return False

    # Use vector similarity to find the best match
    candidate_list = [wp for _, wp in candidates]
    match_idx = find_similar_weak_point(point_text, candidate_list, user_id=user_id, threshold=0.6)
    if match_idx is not None:
        # Map back to original profile index
        original_idx = candidates[match_idx][0]
        wp = profile["weak_points"][original_idx]
        sr = wp.get("sr", {})
        wp["sr"] = sm2_update(sr, score)
        _save_profile(profile, user_id)
        return True

    return False


def init_sr_for_existing_points(user_id: str):
    """Initialize SR state for existing weak points that don't have it yet."""
    profile = _load_profile(user_id)
    changed = False

    for wp in profile.get("weak_points", []):
        if wp.get("improved") or wp.get("archived"):
            continue
        if wp.get("source") == "consolidated" or wp.get("axis") == "performance":
            continue
        if "sr" not in wp:
            wp["sr"] = {
                "interval_days": 1,
                "ease_factor": 2.5,
                "repetitions": 0,
                "next_review": date.today().isoformat(),
                "last_score": None,
            }
            changed = True

    if changed:
        _save_profile(profile, user_id)
