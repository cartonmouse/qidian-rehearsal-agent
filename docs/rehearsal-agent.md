# 奇点排练 Agent 设计说明

## 目标

把剧本、演员档期和排练任务放进同一个可核对的工作区。系统推荐一条“解析 → 人工确认 → 调度 → 排班”的质量控制路径，但不把它当成所有操作的硬性依赖。

## 当前 Agent 边界

### 剧本解析 Agent

- 输入：剧本文本、Markdown 或 PDF。
- 输出：场次、角色、台词、道具、服装需求、来源行号和 Agent trace。
- 解析策略：默认 `auto`；无模型配置时使用本地规则，有配置时尝试 LLM 结构化抽取，失败后按场次回退规则。
- 证据约束：台词和来源行号由服务端保留；即使 LLM 返回了有效行号但改写了台词，服务端也以原文为准；服装候选必须能在当前场次原文中逐字找到，人工审核可以修改场次标题、角色、道具和服装元数据。
- 合同评估：`evals/mock_llm.py` 提供确定性 provider，在真实示例剧本上验证 LLM 结构化输出、原文锚定和适应性对词的角色/来源约束，不需要真实 API Key。

### 人工确认节点

解析结果初始为 `pending`。导演可以确认或修改场次元数据：

- `confirmed`：识别结果无需修改。
- `edited`：导演修改了场次元数据。

确认动作会使旧调度草案失效，避免剧本结构与排班结果不一致。

### 排练调度 Agent

调度 Agent 将每个场次转成任务，并计算：

- 所需演员清单；
- 道具清单；
- 服装清单；
- 预计时长；
- 基于演员、道具和服装库存容量的并行组及分组原因。

默认模式只接受 `confirmed` 或 `edited` 的剧本。导演也可以请求 `preview=true`，得到 `is_preview=true` 的未确认预览；预览用于检查结果，不能被误认为正式排练计划。

### 演员时间池与自动排班

演员可用时间保存在用户级“时间池”中，与剧本解耦。前端优先支持 CSV/TSV 导入，也支持直接粘贴表格内容。下载模板后，在 Excel、WPS 或 Google Sheets 中填写以下四列即可：

```csv
演员,日期,开始时间,结束时间
小林,2026-08-25,19:00,21:00
导演,2026-08-25,19:00,21:00
```

也兼容制表符和竖线分隔的粘贴内容。日期会统一为 `YYYY-MM-DD`，时间会统一为 `HH:MM`；导入后先在预览区检查，再点击“保存档期”写入时间池。重复记录会自动去重，格式错误会定位到具体行。

排班 Agent 为一个任务寻找所需全部演员的最早共同空闲区间，并同时维护演员、道具和服装的已占用时间；服装占用按 `resource_context.costume_capacities` 做容量检查：

- 找到交集：标记 `scheduled` 并记录日期、开始和结束时间；
- 缺少演员档期：标记 `unassigned`，说明缺少哪些演员的时间；
- 有档期但没有共同区间：标记 `unassigned`，原因是演员之间没有共同的空闲时间段，或排练资源没有可用并行容量。

同一并行组中的任务可以复用同一时间窗口；单个演员和道具默认不能被两个任务同时占用，服装则允许不超过库存容量的多个任务并行。这样即使两个场次由不同演员负责，只要共享同一件服装或道具，自动排班也会把它们错开。

每个任务还会记录 `parallel_reason`：没有共同资源时说明“与已有任务没有超出演员、道具或服装库存容量”，发生冲突时列出共享演员/道具或“服装库存容量受限：灰色外套（库存容量 1）”，便于导演理解为什么两个场次不能并行。服装默认按每个场次消耗 1 件；同名库存中状态为 `available` 且数量大于 0 的记录会合计容量，缺少库存或库存不可用时按 1 件保守处理并保留 warning。

当完整排练没有共同档期时，排班 Agent 不直接结束流程，而是为任务返回 `conflict_priority` 和 `alternatives`：如果存在较短共同区间，建议压缩时长；多演员冲突时建议分组排练；缺少演员档期时明确要求补齐对应角色。导演可以调用 `POST /api/rehearsal/scripts/{script_id}/schedule/override` 提交单个确认，或调用 `POST /api/rehearsal/scripts/{script_id}/schedule/override-batch` 一次提交 `{"overrides":[{"task_id":"scene-task-1","date":"2026-08-26","start":"19:00","end":"19:45","room_name":"排练室 A","note":"导演确认"}]}`。如果请求携带 `room_name`，调度 Agent 会调用 `validate_room_booking` 检查用户已有预约以及批次内重叠；跨日期的同一排练室可以分别确认，同日期重叠则返回 `409`。批量接口还会校验整批任务、时长、重复任务、已确认状态、共享演员/道具冲突和服装库存容量；同名服装库存为 2 件时允许两个重叠任务，但第三个任务会返回“超出库存容量 2 件”。成功返回 `atomic=true`、`confirmed_task_ids`、`overridden_count` 以及完整 `schedule`；任一项失败时整批返回 `409`，不会保存部分结果。若导演要修改已经人工确认的单个任务，应使用单任务覆盖接口，避免批量重试产生重复运行记录。

调度草案还会在生成时读取当前用户的配乐时间轴、预算条目、发票元数据、剧本服装需求和服装库存，写入 `resource_context` 快照。快照包含配乐提示点、预算项目、发票记录、服装需求、服装库存、服装并行容量、预计/实际金额、发票总额、已核验金额、未匹配需求和库存风险；当资源非空时，工具调用链会增加 `inspect_rehearsal_resources`，运行记录 trace 会说明读取了哪些资源。实际预算超过预计金额、发票未关联预算项目、仍待核验、服装需求没有库存记录，或服装状态为维修中/缺失/数量为 0 时，只触发“请人工确认”的 warning，不会自动改写预算、确认付款或把不可用服装当成可用。资源在草案生成后发生变化时，需要重新生成调度以获得新的快照。

### 对词 Agent MVP

`POST /api/rehearsal/scripts/{script_id}/line-reading` 推进一轮角色对词。请求包含场次、练习角色、模式、角色语气约束、排练上下文、当前台词索引和演员本轮输入：

- `strict`：对方严格返回原台词，并对演员输入做轻量相似度反馈；不依赖 LLM。
- `adaptive`：把原台词作为事实锚点，请 LLM 根据演员的临场表达、`role_tone` 和 `context_note` 生成对方回应；输出必须保持角色和台词数量一致。
- LLM 未配置或调用失败时：自动回退到原台词，响应标记 `engine=fallback`，不阻断排练。
- `role_tone` 支持 `natural`、`restrained`、`urgent`、`warm`、`cold`、`uncertain`；`context_note` 用于记录本轮导演要求或表演重点，最多 1000 字。

对词页面只允许后端根据保存的原始场次推进 `line_index`，LLM 不能跳转进度、替换演员台词或修改剧本存档。会话会持久化语气和上下文配置，并把最近 8 条 transcript 作为下一轮适应性回应的记忆；续接时如果角色、模式、语气或上下文发生变化，后端会要求重新开始，避免把不同排练意图混在同一个会话里。

### 剧本问答 RAG Agent

`POST /api/rehearsal/scripts/{script_id}/rag` 是面向剧本版本的证据型问答入口。它不是把整部剧本直接塞给模型，而是分成“检索证据 → 组织回答”两个阶段：

1. 先把当前剧本的场次上下文、台词和舞台提示构造成带 `scene_id`、来源类型和 `source_line` 的证据单元；
2. 默认使用本地规则检索，根据问题中的角色、场次、道具和关键词排序；
3. 选择 `retrieval_mode=semantic` 时，若用户配置了 Embedding，则增加向量相似度排序；未配置或调用失败时回退到规则检索；
4. `answer_mode=rules` 直接生成带证据编号的确定性回答，`answer_mode=llm` 或 `auto` 才会尝试让 LLM 组织自然语言。

LLM 回答必须引用检索结果中的证据 ID，并通过 Pydantic 校验；它不能新增场次、行号或剧本事实。没有命中证据时，规则回答会明确表示“无法从当前剧本证实”，LLM 分支也会回退，不允许凭常识补写。响应中的 `engine`、`retrieval_engine` 和 `note` 会说明实际走了规则、语义、LLM 还是降级路径，因此没有 API Key 也可以先演示完整的规则 RAG 闭环。

### Agent 运行记录

`GET /api/rehearsal/agent-runs?limit=50` 提供一条独立的可观察性入口，当前覆盖剧本解析、调度草案、自动排班、对词、资源检查和剧本问答六类运行。每条 `AgentRunRecord` 保存：

- Agent 类型、动作、绑定剧本和运行模式；
- `run_id`、`parent_run_id` 和 `root_run_id`：用于把依赖同一任务的多个 Agent 运行串成一条链；当前调度草案是自动排班的父运行；
- `completed`、`fallback` 或 `failed` 状态，以及后端耗时；
- 结构化 `trace`：每个步骤的名称、状态、摘要和产出数量；
- 降级或未排班等需要关注的原因。

运行记录只保存结构化摘要，不把完整剧本、API Key 或模型原始响应写进审计记录；路径仍通过当前用户 ID 隔离。`GET /api/rehearsal/agent-runs/{run_id}` 可读取单次详情，前端“Agent运行记录”页面会按 `root_run_id` 展示同一任务链。这使得项目可以回答“Agent 经过了哪些步骤、哪一步使用了规则或模型、为什么没有直接给出结果”，并能继续追问“自动排班依赖了哪个调度草案”，而不是只展示最终 JSON。

`GET /api/rehearsal/agent-runs/metrics?window_days=30` 由运行指标 Agent 聚合当前用户的完成、降级、失败、平均耗时和按 Agent 分布，并列出 trace 中出现频率最高的失败步骤。窗口限制为 7 到 365 天，失败率只统计 `status=failed`，不会把正常降级算成失败。LLM Chat 客户端对连接超时、限流和 5xx 等可重试错误最多执行 2 次，重试成功会在解析 warning、对词 note 或 RAG note 中留下记录；资源写入接口不使用自动重试，避免重复预约或重复保存。

### 排练复盘与镜子 Agent

排练反馈是独立于剧本解析的知识资产。`POST /api/rehearsal/feedback` 可以只提交排练日期、参与者、具体产出和原始反馈，也可以选填剧本与场次作为上下文。服务端保存完整原始笔记，再由镜子 Agent 生成：

- `summary`：本次排练的一句话总结；
- `strengths`：已经形成的有效产出或亮点；
- `blockers`：仍然阻塞排练的问题；
- `next_actions`：下一次排练前可执行的动作。

整理方式有三档：`rules` 只使用本地规则，`llm` 请求用户自己的模型，`auto` 优先请求模型。模型未配置、调用失败或返回结构不合规时，Agent 会保留原始反馈并回退到本地规则，响应中的 `engine` 标记为 `fallback`。反馈记录按用户隔离保存，可通过 `GET /api/rehearsal/feedback` 回看。

### 反馈度量 Agent

`GET /api/rehearsal/feedback/metrics?days=30` 是独立于反馈录入的统计入口，支持 7 到 365 天的窗口。Metrics Agent 只读取当前用户已经归档的 `RehearsalFeedbackResponse`，确定性计算：

- 排练次数、具体产出数量、亮点/阻塞/下一步数量；
- 有产出、有阻塞、有下一步的排练覆盖率；
- 去重后的参与者数量和平均参与人数；
- `rules`、`llm`、`fallback` 的使用次数；
- 高频亮点、高频阻塞、每日活动趋势和最近记录指针。

它不会把这些计数合成为未经证实的“排练质量分数”，响应中的 `recent_sessions.record_id` 可以回到原始反馈。没有记录时仍返回完整的零值趋势，便于前端稳定展示空状态。

### 剧本版本差异追踪 Agent

`POST /api/rehearsal/scripts/{script_id}/diff` 将路径中的目标版本与请求体中的 `compare_script_id` 作为旧版本进行比较。版本差异 Agent 不让 LLM 猜测变化，而是按场次编号对齐保存的结构化结果，再使用原始台词顺序和 `SourceSpan` 计算：

- 新增、删除或未变化的场次；
- 场次标题、角色清单和道具清单变化；
- 新增、删除、修改的台词，以及旧行号/新行号；
- 受影响演员、道具和需要重新核对台词的角色。

响应还会生成 `downstream_impacts`：每个受影响场次分别给出 `schedule`、`line-reading` 或 `resource` 类型、严重级别、受影响演员/道具、触发原因和建议动作，并用 `requires_schedule_review`、`requires_line_reading_review`、`requires_resource_review` 汇总是否需要复核。`resource` 影响还会包含 `resource_audit_matches`，按道具名称匹配当前用户近期资源审计中的新增、修改或删除记录。版本追踪页面会把这些提醒展示成可操作卡片，分别跳转到演员排练表、对词训练和带复核上下文的资源管理；它不会自动覆盖已有排班或对词进度，最终动作仍由导演确认。

因此剧本版本变化可以直接传递给调度 Agent 和导演人工确认环节。版本追踪页面只展示用户自己保存的剧本，不改变任何一个版本的原始内容。

### 舞台可视化 Stage Agent

解析器会把括号中的舞台提示保存为 `stage_directions`，包括提示原文、类型和 `source_line`。即使角色只出现在“上场/下场”提示中、没有角色台词，也会被纳入场景角色清单。

`GET /api/rehearsal/scripts/{script_id}/stage/{scene_id}` 根据这些证据生成：

- `actors`：角色头像所需的名称、在台/离台状态、九宫格位置和来源行号；
- `props`：道具名称、推断位置和出现行号；
- `events`：按原文行号排序的上场、下场、走位、道具和台词事件；
- `warnings`：没有明确走位或舞台提示无法匹配角色时的人工确认提醒。

位置推断只使用舞台提示中的“左/右、前/后、中央”等明确词语；没有证据时使用默认布局或 `unknown`，不会让模型猜测具体走位。

### 资源管理 Resource Agent

资源管理是独立入口，不要求先解析剧本。`GET/PUT /api/rehearsal/resources/inventory` 用用户隔离的 `data/users/{id}/rehearsal/resources/inventory.json` 保存道具和服装库存；每条记录包含类别、数量、状态、存放位置和备注。库存状态由剧团成员人工确认，Agent 不会把“有库存记录”直接当成“可用”。所有资源写入都会由 Resource Audit Agent 对比写入前后的结构化快照，保存到用户隔离的 `rehearsal/resources/audit.json`。

`GET /api/rehearsal/resources/audit?limit=50` 返回库存、排练室、配乐、预算和发票的最近变更；可以追加 `resource_type`、`change_type` 和 `query` 筛选资源类型、变更动作和资源名称/摘要。每条记录会指出新增、修改或删除的资源、变化字段和摘要。审计只记录结构化元数据，不把凭证文件或模型密钥写入记录。

`POST /api/rehearsal/resources/rooms` 保存排练室预约，并在写入前检查同一房间、同一天的区间是否重叠。边界相接（例如上一场 19:00-20:00，下一场 20:00-21:00）允许；实际重叠返回 `409`，避免把冲突留给排练当天处理。

`POST /api/rehearsal/scripts/{script_id}/resources/check` 可以传入 `scene_id` 做单场检查，也可以传空值做全剧本检查。Resource Agent 的规则是：

- 单场检查按场次中出现的道具需求数量匹配 `category=prop` 的库存；
- `status=available` 的数量满足需求时标记 `ready`；
- 没有足够可用数量但存在维修库存时标记 `maintenance`；
- 没有匹配记录或没有可用数量时标记 `missing`；
- 全剧本检查按每种道具至少一件计算，并给出“请切换到单场检查”的提醒，避免把连续场次误当成同时需要多份道具。

响应同时给出每一项的需求数量、可用数量、匹配原因、汇总和 warnings。服装需求只从剧本明确出现的服装词生成，LLM 返回的候选必须通过原文匹配；导演确认后，调度 Agent 会把它们与服装库存逐项对照。系统不根据角色身份或场景做隐含猜测。

### 音乐、预算与发票 Resource Finance Agent

资源管理的财务和音乐部分使用独立的用户隔离文件：

- `GET/PUT /api/rehearsal/resources/music` 保存曲目、场次、提示类型、开始/结束秒数和排练备注；服务端拒绝反向时间区间；
- `GET/PUT /api/rehearsal/resources/budget` 保存道具、服装、音乐、场地等预算项目的预计金额、实际金额和人工状态；
- `GET/PUT /api/rehearsal/resources/invoices` 保存供应商、日期、金额、核验状态和可选的预算项目关联；当前 MVP 只保存发票元数据，不上传文件；
- `GET /api/rehearsal/resources/finance-summary` 由 Resource Finance Agent 汇总预算、实际、发票、已核验金额，并提示超支、待核验和未关联票据。

预算实际金额与发票金额故意分开：一张待核验发票不能自动变成已付款，一张没有 `budget_item_id` 的发票也不会被强行归入某个预算项目。这样财务 Agent 给出的是可解释的风险提醒，而不是未经人工确认的记账结果。

### 场记档案 Logbook Agent

场记是知识资产模块的独立入口。`POST /api/rehearsal/logbook` 接收排练日期、记录人、记录类型、现场原话和标签，并允许选填 `script_id`、`scene_id` 与 `source_line`。服务端会校验剧本/场次确实属于当前用户，再保存到 `data/users/{id}/rehearsal/logbook/`。

Logbook Agent 的边界很明确：它会根据记录类型补充一个检索标签（例如 `blocking` 补充“走位”），去重用户标签，保存剧本和场次标题；现场原话、原文行号和记录日期保持不变。它不会把导演的模糊表达改写成“事实”，也不会调用 LLM 猜测排练发生了什么。

场记与“排练复盘 / 镜子 Agent”互补：场记适合记录一条条现场事实和可回指证据，复盘适合在一次排练结束后从多条反馈中生成亮点、阻塞项和下一步动作。两者都保留原始输入，再由知识资产入口继续沉淀可复用内容。

### 演员建议收件箱 Suggestion Agent

`POST /api/rehearsal/suggestions` 是面向演员的低门槛入口。建议可以关联剧本和场次，也可以完全独立提交；服务端会验证关联上下文属于当前用户。原始 `content` 永远保留，建议记录另外保存提交人、分类、优先级、状态、导演回应和更新时间。

Suggestion Agent 的第一版只做可解释判断：分类为 `safety`，或内容明确包含“安全、危险、受伤、疼、过敏、设备故障、冲突”等词时，标记 `priority=high`；其他建议为 `normal`。这不是情绪或价值判断，而是把需要尽快人工确认的信号从收件箱中凸显出来。

导演可以通过 `PATCH /api/rehearsal/suggestions/{suggestion_id}` 把状态从 `new` 流转到 `reviewed`、`accepted` 或 `archived`，并写下具体处理回应。状态和回应会写回用户隔离存储，便于之后做排练度量或回溯“建议是否被采纳”。

### 格言表与宣传文案 Knowledge Asset Agents

知识资产入口把“值得留下的话”和“对外表达”拆成两个可独立使用的 Agent：

- `POST /api/rehearsal/knowledge/mottos` 保存格言。服务端保留 `text`、作者、来源和可选的剧本/场次上下文，只补充主题标签并去重用户标签；收藏状态由导演或演员人工切换。
- `POST /api/rehearsal/knowledge/promo` 生成宣传文案。输入可以只有作品名和 brief，也可以关联已保存剧本，Agent 只读取剧名、场次标题和角色名等结构化事实，输出标题、短文案、长文案和话题标签。

宣传文案支持三种模式：`rules` 只走本地确定性模板，`llm` 只尝试用户配置的模型，`auto` 优先使用 LLM、失败后自动降级。LLM 返回必须通过 JSON/Pydantic 校验；连接失败、返回非结构化文本或模型未配置时，响应标记 `engine=fallback` 并保留可直接使用的规则结果。这样既能展示 Agent 的模型分支，也不会让知识资产入口依赖 API Key 才能打开。

## 为什么不是强制流水线

调度任务自动生成确实依赖结构化场次信息，但演员档期、道具库存、场记和反馈记录不依赖剧本解析。因此前端使用“推荐路径（可跳过）”表达依赖关系：

1. 推荐先解析并人工确认，获得质量更高的正式调度；
2. 可以先录入演员时间池；
3. 可以对待确认解析结果生成调度预览；
4. 可以在没有剧本的情况下先记录排练反馈；
5. 可以在保存两个剧本版本后独立查看差异；
6. 可以在没有剧本的情况下先保存格言、生成不关联剧本的宣传文案；
7. 剧本问答必须选择一个已保存的剧本版本，但它不要求先生成调度或排班；
8. 只有正式草案才代表可直接执行的排练计划。

这种设计把 UI 导航和后端数据依赖分开：入口可以灵活，正式结果仍有质量门槛。

## 前端入口

侧栏已经切换为剧团工作流：

- `排练工作台`：输入或上传剧本，运行剧本解析 Agent，进行人工确认，并查看调度预览。
- `演员排练表`：导入或粘贴演员档期，预览并保存时间池，选择已保存的剧本，生成场次任务，查看并行组并执行自动排班。
- `对词训练`：选择剧本、场次和角色，使用原词模式或适应性模式进行逐句对词。
- `剧本问答`：针对一个已保存剧本版本提问，查看检索证据、原文行号和回答引擎路径。
- `排练复盘`：独立记录一次排练的产出和原始反馈，使用镜子 Agent 生成结构化复盘并回看历史档案。
- `排练度量`：按 7/30/90 天查看排练趋势、产出覆盖率、高频亮点/阻塞和 Agent 路径。
- `Agent运行记录`：回看解析、调度、排班、对词和剧本问答的结构化步骤、耗时和降级原因。
- `版本追踪`：选择两个已保存剧本版本，查看场次、资源和台词差异。
- `舞台可视化`：选择一个剧本场次，查看角色头像、道具位置和上下场动态列表。
- `资源管理`：维护道具/服装库存，预约排练室，按剧本或场次运行排练前道具就绪检查。
- `音乐与预算`：记录配乐时间轴，维护预算和发票元数据，查看 Resource Finance Agent 的金额关联与风险提示。
- `场记档案`：记录现场原话，关联剧本/场次/行号，并按类型和标签回看历史知识资产。
- `建议收件箱`：提交演员建议，查看高优先级提醒，更新处理状态并留下导演回应。
- `知识资产`：保存不改写的排练格言，或基于剧本结构生成可解释的宣传文案。
- `设置`：保留基础账号和模型服务配置。

原 TechSpar 的面试训练、简历和录音等路由暂时保留在代码中，但不再作为奇点剧团的主侧栏入口，后续可以按需要彻底拆除或改造成剧团模块。

## 面试时可解释的工程点

- Human-in-the-loop：让导演确认高风险元数据，而不是让模型直接改变原始台词证据。
- Structured output：Agent 之间通过 Pydantic 模型传递场次、任务和档期，不依赖自然语言拼接。
- Graceful degradation：LLM 不可用时规则解析仍能完成最小闭环；调度预览与正式草案区分风险。
- Resource-aware scheduling：并行组和自动排班都基于演员、道具和服装容量资源集合，而不是只按场次顺序。
- User isolation：剧本、调度和演员时间池均按用户隔离保存。
- Explainability：每个调度任务带来源场次、演员、道具、预计时长、并行分组原因和未排班原因；每条复盘保留原始笔记并展示 Agent 的结构化依据。
- Version evidence：版本差异按场次编号、台词顺序和 `SourceSpan` 对齐，变更可以回指旧行号和新行号。
- Stage evidence：舞台提示和台词事件保留 `source_line`，没有位置证据的角色或道具明确标记为待人工确认。
- Resource explainability：资源检查保留需求数量、可用数量和“缺失/维修中”的具体原因；排练室预约用后端区间冲突校验保证一致性。
- Finance boundary：预算实际金额、发票金额和核验状态分开保存；财务 Agent 只输出超支/未关联/待核验提醒，不自动确认付款。
- Logbook evidence：场记保留原始内容和可选 `source_line`，Agent 只做去重和上下文补充，不把推测写回事实记录。
- Suggestion triage：建议的高优先级只来自明确安全信号和人工选择的安全分类，状态流转与导演回应可追踪，原始意见不被模型改写。
- Knowledge asset boundary：格言 Agent 保留原文，宣传文案 Agent 只引用已保存结构和 brief；LLM 返回经过结构校验，失败时有规则降级并报告 engine。
- RAG evidence boundary：剧本问答先检索带 `source_line` 的证据，再组织回答；LLM 只能引用证据 ID，无命中时拒答，`engine` 和 `retrieval_engine` 可审计实际路径。
- Metrics boundary：度量 Agent 只聚合已归档字段，并保留记录 ID 作为回指，不把有限样本推断成排练质量结论。
- Agent observability：核心 Agent 将动作、模式、耗时、结构化步骤和降级原因写入用户隔离的运行记录，前端支持按次回看；审计摘要不携带 API Key 或完整原文。

## 关键 API

- `POST /api/rehearsal/scripts/parse`
- `PUT /api/rehearsal/scripts/{script_id}/review`
- `GET/PUT /api/rehearsal/availability`
- `POST /api/rehearsal/scripts/{script_id}/schedule/draft`
- `POST /api/rehearsal/scripts/{script_id}/schedule/plan`
- `POST /api/rehearsal/scripts/{script_id}/schedule/override`
- `POST /api/rehearsal/scripts/{script_id}/line-reading`
- `POST /api/rehearsal/scripts/{script_id}/rag`
- `GET /api/rehearsal/agent-runs?limit=50`
- `GET /api/rehearsal/agent-runs/metrics?window_days=30`
- `GET /api/rehearsal/agent-runs/{run_id}`
- `POST /api/rehearsal/feedback`
- `GET /api/rehearsal/feedback`
- `GET /api/rehearsal/feedback/metrics?days=30`
- `GET /api/rehearsal/feedback/{record_id}`
- `POST /api/rehearsal/scripts/{script_id}/diff`（资源影响包含匹配的 `resource_audit_matches`）
- `GET /api/rehearsal/scripts/{script_id}/stage/{scene_id}`
- `GET/PUT /api/rehearsal/resources/inventory`
- `GET /api/rehearsal/resources/audit?limit=50&resource_type=&change_type=&query=`
- `GET/POST /api/rehearsal/resources/rooms`
- `DELETE /api/rehearsal/resources/rooms/{booking_id}`
- `POST /api/rehearsal/scripts/{script_id}/resources/check`
- `GET/PUT /api/rehearsal/resources/music`
- `GET/PUT /api/rehearsal/resources/budget`
- `GET/PUT /api/rehearsal/resources/invoices`
- `GET /api/rehearsal/resources/finance-summary`
- `POST /api/rehearsal/logbook`
- `GET /api/rehearsal/logbook`
- `DELETE /api/rehearsal/logbook/{log_id}`
- `POST /api/rehearsal/suggestions`
- `GET /api/rehearsal/suggestions`
- `PATCH /api/rehearsal/suggestions/{suggestion_id}`
- `DELETE /api/rehearsal/suggestions/{suggestion_id}`
- `POST /api/rehearsal/knowledge/mottos`
- `GET /api/rehearsal/knowledge/mottos`
- `PATCH /api/rehearsal/knowledge/mottos/{motto_id}`
- `DELETE /api/rehearsal/knowledge/mottos/{motto_id}`
- `POST /api/rehearsal/knowledge/promo`
- `GET /api/rehearsal/knowledge/promo`

## 验证方式

```bash
# 前端
cd frontend
npm run build

# 后端语法
python -m compileall -q backend

# 排练 Agent 回归测试（当前环境也可直接调用测试函数）
python -c "import tests.test_rehearsal_agent as t; [getattr(t, n)() for n in dir(t) if n.startswith('test_')]"
```
