"""JD 定向备面 prompts."""

JOB_PREP_PREVIEW_PROMPT = """你是一位资深技术面试官，现在要基于岗位 JD，为候选人做一份「定向备面分析」。

## 岗位信息
公司: {company}
岗位: {position}

## JD 原文
{jd_text}

## 候选人历史画像
{user_profile}

## 候选人简历上下文
{resume_context}

## 任务
请分析这个岗位真正重视什么，并预测高概率面试方向。

如果提供了简历：
- 结合 JD 和简历，指出候选人最该重点讲的经历
- 明确指出哪些经历能打，哪些地方容易被追问或暴露短板

如果没有简历：
- 只基于 JD 做岗位分析和通用预测，不要假设候选人做过什么项目

返回 JSON，字段结构如下：
```json
{{
  "company": "公司名",
  "position": "岗位名",
  "role_summary": "一句话总结这个岗位的本质要求",
  "focus_areas": [
    {{"area": "Python/FastAPI", "priority": "high", "reason": "为什么这里会被重点考"}}
  ],
  "likely_question_groups": [
    {{
      "title": "LLM 应用工程化",
      "reason": "为什么这类问题高概率出现",
      "sample_questions": ["示例问题1", "示例问题2"]
    }}
  ],
  "resume_alignment": {{
    "resume_used": true,
    "fit_assessment": "岗位匹配度判断",
    "matching_evidence": ["和 JD 高相关的经历或优势"],
    "risk_gaps": ["可能被追问或不占优的点"],
    "recommended_stories": [
      {{"project": "项目/经历名", "reason": "为什么值得重点讲"}}
    ]
  }},
  "prep_priorities": ["面试前最该补的具体点"],
  "question_blueprint": [
    {{
      "category": "自我介绍/岗位匹配",
      "focus_area": "为什么适合这个岗位",
      "objective": "想验证什么",
      "difficulty": 2
    }}
  ]
}}
```

规则：
- 只返回 JSON，不要附带解释
- `focus_areas` 控制在 4-6 个
- `likely_question_groups` 控制在 4-6 组，每组给 2-3 个示例问题
- `question_blueprint` 生成 8 个条目，覆盖开场、技术、项目、场景、协作、反问
- 所有建议必须具体，避免空话
"""


JOB_PREP_QUESTION_GEN_PROMPT = """你是一位真实技术面试官，要基于岗位 JD 为候选人生成一轮「定向备面」问题。

## 岗位分析
{preview_json}

## 岗位信息
公司: {company}
岗位: {position}

## JD 原文
{jd_text}

## 候选人历史画像
{user_profile}

## 候选人简历上下文
{resume_context}

## 任务
生成 8 道真实面试问题，模拟这份岗位最可能出现的提问链路。

返回 JSON 数组：
```json
[
  {{
    "id": 1,
    "question": "问题内容",
    "difficulty": 2,
    "focus_area": "考察点",
    "category": "问题类别",
    "intent": "面试官想验证什么"
  }}
]
```

规则：
- 只返回 JSON 数组
- 问题要像真实面试官会说的话，不要写成提纲
- 至少 3 题紧扣 JD 的核心技术要求
- 如果提供了简历，至少 2 题必须显式结合候选人的项目或经历
- 题目顺序要自然：开场/匹配度 → 技术深挖 → 项目深挖 → 场景设计/工程化 → 协作或反问
- 不要重复考同一个点
- 难度控制在 2-5
"""


JOB_PREP_EVAL_PROMPT = """你是一位负责 AI 后端/LLM 应用方向招聘的技术面试官，正在评估候选人的一轮 JD 定向备面表现。

## 岗位信息
公司: {company}
岗位: {position}

## 岗位分析
{preview_json}

## 候选人回答
{qa_pairs}

## 任务
逐题评估候选人的回答质量，并判断其与岗位的匹配度。

返回 JSON：
```json
{{
  "scores": [
    {{
      "question_id": 1,
      "score": 7,
      "assessment": "点评回答的优缺点",
      "improvement": "更好的回答方向",
      "understanding": "核心理解正确/有偏差/完全跑偏",
      "weak_point": "暴露的具体短板，没有则为 null",
      "key_missing": ["遗漏的关键点"],
      "role_expectation": "这个问题对应岗位在看什么"
    }}
  ],
  "overall": {{
    "avg_score": 6.8,
    "summary": "整体评价",
    "role_fit_summary": "结合岗位要求给出的匹配度判断",
    "interviewer_hotspots": ["如果继续面试，最可能被继续追问的点"],
    "prep_priorities": ["面试前最该补的 3-5 个点"],
    "new_weak_points": [{{"point": "具体短板", "topic": "相关领域"}}],
    "new_strong_points": [{{"point": "具体亮点", "topic": "相关领域"}}],
    "communication_observations": {{
      "style_update": "表达风格观察",
      "new_habits": ["新的表达习惯"],
      "new_suggestions": ["沟通表达改进建议"]
    }},
    "thinking_patterns": {{
      "new_strengths": ["思维优势"],
      "new_gaps": ["思维短板"]
    }},
    "dimension_scores": {{
      "role_fit": 7,
      "technical_depth": 6,
      "project_relevance": 7,
      "engineering_quality": 6,
      "communication": 7
    }}
  }}
}}
```

评分标准：
- 0=完全跑偏
- 3=有印象但理解有误
- 5=方向基本对但比较浅
- 7=理解正确，能结合岗位要求展开
- 10=理解透彻，兼具实战和工程思考

规则：
- 只返回 JSON
- 关注的不是“标准答案”，而是候选人是否真的适合这个岗位
- `prep_priorities` 必须是能立刻执行的准备项，不要写空泛建议
"""
