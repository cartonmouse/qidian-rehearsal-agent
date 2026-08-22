"""Helpers for review markdown rendering."""


def format_solo_review(topics_covered: list, overall: dict) -> str:
    """Format solo mode evaluation into a readable review."""
    lines = [f"## 整体评价\n\n{overall.get('summary', '')}\n\n**平均分: {overall.get('avg_score', '-')}/10**\n"]

    if topics_covered:
        lines.append("---\n\n## 涉及知识点\n")
        for item in topics_covered:
            score = item.get("score", "-")
            lines.append(f"### {item.get('topic', '未知')} — {score}/10")
            if item.get("assessment"):
                lines.append(f"**评价**: {item['assessment']}")
            if item.get("understanding"):
                lines.append(f"**理解程度**: {item['understanding']}")
            if item.get("errors"):
                lines.append(f"**错误**: {', '.join(item['errors'])}")
            if item.get("missing"):
                lines.append(f"**遗漏**: {', '.join(item['missing'])}")
            lines.append("")

    if overall.get("new_weak_points"):
        lines.append("---\n\n## 薄弱点")
        for item in overall["new_weak_points"]:
            lines.append(f"- {item.get('point', item) if isinstance(item, dict) else item}")

    if overall.get("new_strong_points"):
        lines.append("\n## 亮点")
        for item in overall["new_strong_points"]:
            lines.append(f"- {item.get('point', item) if isinstance(item, dict) else item}")

    return "\n".join(lines)


def format_drill_review(questions, answers, scores, overall) -> str:
    """Format drill evaluation into a readable review string."""
    answer_map = {answer["question_id"]: answer["answer"] for answer in answers}
    score_map = {score["question_id"]: score for score in scores}

    lines = [f"## 整体评价\n\n{overall.get('summary', '')}\n\n**平均分: {overall.get('avg_score', '-')}/10**\n"]
    lines.append("---\n\n## 逐题复盘\n")

    for question in questions:
        question_id = question["id"]
        score = score_map.get(question_id, {})
        answer = answer_map.get(question_id, "")

        if not answer:
            lines.append(f"### Q{question_id} ({question.get('focus_area', '')}) — 未作答")
            lines.append(f"**题目**: {question['question']}\n")
            continue

        lines.append(f"### Q{question_id} ({question.get('focus_area', '')}) — {score.get('score', '-')}/10")
        lines.append(f"**题目**: {question['question']}")
        lines.append(f"**你的回答**: {answer}")
        if score.get("assessment"):
            lines.append(f"**点评**: {score['assessment']}")
        if score.get("improvement"):
            lines.append(f"**改进建议**: {score['improvement']}")
        if score.get("understanding"):
            lines.append(f"**理解程度**: {score['understanding']}")
        if score.get("key_missing"):
            lines.append(f"**遗漏关键点**: {', '.join(score['key_missing'])}")
        lines.append("")

    if overall.get("new_weak_points"):
        lines.append("---\n\n## 薄弱点")
        for item in overall["new_weak_points"]:
            lines.append(f"- {item.get('point', item) if isinstance(item, dict) else item}")

    if overall.get("new_strong_points"):
        lines.append("\n## 亮点")
        for item in overall["new_strong_points"]:
            lines.append(f"- {item.get('point', item) if isinstance(item, dict) else item}")

    return "\n".join(lines)


def format_job_prep_review(questions, answers, scores, overall, meta) -> str:
    """Format JD prep evaluation into a readable review string."""
    answer_map = {answer["question_id"]: answer["answer"] for answer in answers}
    score_map = {score["question_id"]: score for score in scores}

    title = meta.get("position") or "目标岗位"
    company = meta.get("company")
    heading = f"{company} / {title}" if company else title

    lines = [f"## 岗位画像\n\n**目标岗位**: {heading}\n"]

    if meta.get("preview", {}).get("role_summary"):
        lines.append(f"\n**岗位本质**: {meta['preview']['role_summary']}\n")

    lines.append(f"\n## 整体评价\n\n{overall.get('summary', '')}\n")
    lines.append(f"\n**平均分: {overall.get('avg_score', '-')}/10**")

    if overall.get("role_fit_summary"):
        lines.append(f"\n**岗位匹配度**: {overall['role_fit_summary']}")

    if overall.get("interviewer_hotspots"):
        lines.append("\n\n## 高风险追问点")
        for item in overall["interviewer_hotspots"]:
            lines.append(f"- {item}")

    if overall.get("prep_priorities"):
        lines.append("\n## 面试前优先补强")
        for item in overall["prep_priorities"]:
            lines.append(f"- {item}")

    lines.append("\n---\n\n## 逐题复盘\n")
    for question in questions:
        question_id = question["id"]
        score = score_map.get(question_id, {})
        answer = answer_map.get(question_id, "")

        if not answer:
            lines.append(f"### Q{question_id} ({question.get('category', '未分类')}) — 未作答")
            lines.append(f"**题目**: {question['question']}\n")
            continue

        lines.append(
            f"### Q{question_id} ({question.get('category', '未分类')} / {question.get('focus_area', '')})"
            f" — {score.get('score', '-')}/10"
        )
        lines.append(f"**题目**: {question['question']}")
        lines.append(f"**你的回答**: {answer}")
        if score.get("role_expectation"):
            lines.append(f"**岗位在看什么**: {score['role_expectation']}")
        if score.get("assessment"):
            lines.append(f"**点评**: {score['assessment']}")
        if score.get("improvement"):
            lines.append(f"**改进建议**: {score['improvement']}")
        if score.get("understanding"):
            lines.append(f"**理解程度**: {score['understanding']}")
        if score.get("key_missing"):
            lines.append(f"**遗漏关键点**: {', '.join(score['key_missing'])}")
        lines.append("")

    if overall.get("new_weak_points"):
        lines.append("---\n\n## 薄弱点")
        for item in overall["new_weak_points"]:
            lines.append(f"- {item.get('point', item) if isinstance(item, dict) else item}")

    if overall.get("new_strong_points"):
        lines.append("\n## 亮点")
        for item in overall["new_strong_points"]:
            lines.append(f"- {item.get('point', item) if isinstance(item, dict) else item}")

    return "\n".join(lines)
