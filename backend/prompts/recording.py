"""录音复盘 Prompts — 双人模式结构化 + 单人模式整体评估。"""

# ── 双人模式：从转写文本提取 Q&A 对 ──

RECORDING_STRUCTURE_PROMPT = """你是面试记录分析专家。以下是一段面试录音的转写文本，可能包含说话人标记。

## 转写文本
{transcript}

## 任务
分析这段对话，识别面试官和候选人，提取出所有 Q&A 对。

### 角色判断规则
- 提问多的一方通常是面试官
- 回答/解释多的一方通常是候选人
- 说话人标记可能不完全准确，以对话内容和语境为准

### 提取规则
- 面试官的寒暄/过渡语（"好的"、"下一个问题"）不算独立问题
- 面试官连续追问同一话题的多个问题，合并为一个 Q&A
- 候选人的回答如果被打断后继续，合并为完整回答
- 跳过纯粹的开场白和结束语

返回 JSON（只返回 JSON，不要其他内容）：
```json
{{
    "qa_pairs": [
        {{
            "id": 1,
            "question": "面试官的完整问题",
            "answer": "候选人的完整回答",
            "focus_area": "这道题考察的知识点（简短）",
            "topic": "所属技术领域（如 python / rag / agent 等）"
        }}
    ],
    "metadata": {{
        "total_questions": 5,
        "topics_covered": ["领域1", "领域2"],
        "difficulty_impression": "简单/中等/较难"
    }}
}}
```"""


# ── 双人模式：Q&A 评估（录音专用，不绑定单一领域）──

RECORDING_DUAL_EVAL_PROMPT = """你是资深技术面试官，正在评估候选人在一场真实面试中的表现。

## 候选人画像
{profile_summary}

请在评估时特别注意：
- 候选人的已知薄弱点在本次面试中是否有改善或继续暴露
- 是否出现了画像中未记录的新薄弱点
- 与历史表现相比，整体是进步还是退步

## 候选人的回答
{qa_pairs}

## 任务
逐题评估，然后给出整体分析。候选人用自己的话说，只要核心理解对就给分。

返回 JSON（只返回 JSON，不要其他内容）：
```json
{{
    "scores": [
        {{
            "question_id": 1,
            "score": 7,
            "assessment": "点评回答的优缺点，2-3句话",
            "improvement": "具体的改进建议",
            "understanding": "核心理解正确/有偏差/完全跑偏",
            "weak_point": "暴露的薄弱点，没有则为 null",
            "key_missing": ["遗漏的关键点"]
        }}
    ],
    "overall": {{
        "avg_score": 6.5,
        "summary": "整体表现的一段话评价",
        "new_weak_points": [{{"point": "薄弱点描述", "topic": "所属领域"}}],
        "new_strong_points": [{{"point": "强项描述", "topic": "所属领域"}}],
        "communication_observations": {{
            "style_update": "回答风格观察",
            "new_habits": ["表达习惯"],
            "new_suggestions": ["改进建议"]
        }},
        "thinking_patterns": {{
            "new_strengths": ["思维优势"],
            "new_gaps": ["思维短板"]
        }},
        "longitudinal": {{
            "improved_points": ["相比画像记录有改善的点"],
            "persisting_points": ["画像中已有且本次仍暴露的薄弱点"],
            "new_concerns": ["本次新发现的、画像中未记录的问题"]
        }}
    }}
}}
```

评分标准：
- 0=完全跑偏 3=有印象但理解有误 5=大方向对但浅 7=理解正确有自己思考 10=深入透彻
- 关注：是否理解本质、有没有自己的思考、能不能举例
"""


# ── 单人模式：整体技术评估 ──

RECORDING_SOLO_EVAL_PROMPT = """你是资深技术面试官，正在评估一段候选人的技术表达录音。

## 候选人画像
{profile_summary}

请在评估时特别注意：
- 候选人的已知薄弱点在本次表达中是否有改善或继续暴露
- 与历史表现相比，理解深度是否有进步

## 候选人的技术表达
{transcript}

## 任务
这是候选人在面试后的录音/复述，只有候选人一个人的声音。你需要从他的表达中评估他的技术水平。

### 评估维度
1. **知识点覆盖**：他谈到了哪些知识点？有没有重要遗漏？
2. **理解深度**：每个知识点是真的理解了还是在背概念？有没有自己的思考？
3. **准确性**：有没有明显的技术错误或混淆？
4. **表达质量**：说得有没有条理？能不能让人听懂？

### 评分标准
- 0=完全跑偏 3=有印象但理解有误 5=大方向对但浅 7=理解正确有自己思考 10=深入透彻

返回 JSON（只返回 JSON，不要其他内容）：
```json
{{
    "topics_covered": [
        {{
            "id": 1,
            "topic": "知识点名称",
            "domain": "所属技术领域（如 python / rag / agent 等）",
            "score": 7,
            "assessment": "对这个知识点的评价，2-3句",
            "understanding": "核心理解正确/有偏差/完全跑偏",
            "errors": ["具体错误描述，没有则为空数组"],
            "missing": ["遗漏的关键点"]
        }}
    ],
    "overall": {{
        "avg_score": 6.5,
        "summary": "整体表现的一段话评价",
        "new_weak_points": [{{"point": "薄弱点描述", "topic": "所属领域"}}],
        "new_strong_points": [{{"point": "强项描述", "topic": "所属领域"}}],
        "communication_observations": {{
            "style_update": "表达风格观察",
            "new_habits": ["表达习惯"],
            "new_suggestions": ["改进建议"]
        }},
        "thinking_patterns": {{
            "new_strengths": ["思维优势"],
            "new_gaps": ["思维短板"]
        }},
        "longitudinal": {{
            "improved_points": ["相比画像记录有改善的点"],
            "persisting_points": ["画像中已有且本次仍暴露的薄弱点"],
            "new_concerns": ["本次新发现的、画像中未记录的问题"]
        }}
    }}
}}
```"""
