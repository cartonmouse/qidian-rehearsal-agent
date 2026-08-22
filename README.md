# qidian-rehearsal-agent

奇点排练 Agent：面向话剧排练的智能协作平台。

项目代号是 `qidian`，名字来自“奇点”——剧团的中心，也象征剧本、演员、场记、道具和排练 Agent 汇聚后产生新的创作秩序。

## 当前进度

第一阶段已经打通“剧本解析 Agent”最小闭环：

```text
剧本文本 / Markdown / PDF
        ↓
摄取并保留原始行号
        ↓
识别场次
        ↓
并行提取角色、台词、道具、服装需求
        ↓
校验与保守修复
        ↓
待人工确认：修改场次、角色、道具
        ↓
确认后按用户隔离保存结构化排练数据
```

当前接口会返回每个场次、角色、台词、道具、服装需求和 Agent trace，并为台词、服装候选与场次保留原剧本行号，方便导演人工核对。解析默认使用 `auto` 策略：没有配置 LLM 时走本地可解释规则，配置后按场次并行执行 LLM 结构化抽取；单场调用失败会自动回退规则解析。Embedding 不是剧本解析节点的前置条件。

解析结果初始状态为 `pending`。导演可以在前端人工确认或修改每场的标题、角色、道具和服装；台词原文与来源行号由服务端保留，LLM 服装候选只有在原文可核对时才会进入结果。审核状态变为 `confirmed` 或 `edited` 后，结果才适合作为后续排练调度的输入。

已确认的剧本可以交给排练调度 Agent，生成每场的演员清单、道具清单、服装清单、预计时长和资源不冲突的并行任务组。服装会同时参与并行冲突判断：同名可用库存数量会合计为并行容量，库存为 2 件时允许两个场次同时进行，容量不足时在 `parallel_reason` 中解释；库存不存在或状态不可用时按 1 件保守处理并给出可解释 warning，等待人工确认。目前默认产出是正式调度草案；如果导演想先看结果，也可以在人工确认前请求 `preview=true`，系统会返回带 `is_preview=true` 标记的未确认预览，不会把它冒充为正式排练计划。人工确认后重新生成即可得到正式草案。

当前已接入第一版自动排班：在“演员排练表”中导入 CSV/TSV，或粘贴“演员、日期、开始时间、结束时间”四列数据后，系统寻找一场所需全部演员的最早共同空闲区间；找不到交集时保留未排班原因。并行组中的演员资源不冲突场次可以被安排在同一时间。

每个调度任务还会记录并展示分组原因：没有共同演员、道具或超出服装库存容量的场次可以进入同一并行组；发生冲突时列出共享资源或容量限制，便于导演解释为什么任务需要错开。

调度 Agent 还会返回可审计的工具调用链：`inspect_script` 检查人工确认门槛，`extract_scene_requirements` 提取演员/道具/服装/时长，`group_parallel_tasks` 按演员、道具和服装库存容量划分并行组，`find_common_actor_slot` 查找共同档期，最后由 `validate_schedule` 校验已排、未排和冲突数量。工作台会同时展示每次调用的参数摘要、结果和降级状态。

档期导入兼容 Excel、WPS 和 Google Sheets 导出的表格。前端提供模板下载、行级格式校验和导入预览，也兼容制表符或竖线分隔的粘贴内容；确认预览后点击“保存档期”，时间池即可被不同剧本重复使用。

第一版对词 Agent 已接入侧栏“对词训练”：可以选择剧本、场次和角色，按“原词模式”逐句练习，也可以选择“适应性模式”让 LLM 根据演员临场表达生成对方回应。原词模式不需要模型服务；适应性模式在 LLM 未配置或调用失败时自动回退到原台词，并保留来源行号。对词页面还支持角色语气约束和本轮排练上下文；后端会保存游标、完整 transcript、引擎统计、语气、上下文和下一句原词，续接时把最近 8 条记录传给适应性 Agent；后端不会信任客户端跳跃提交的 `line_index`，也不会允许中途更换同一会话的排练意图。

排练复盘已经接入侧栏“排练复盘”：一次排练可以独立记录日期、参与者、具体产出和原始反馈；镜子 Agent 会生成总结、已形成的亮点、待解决的阻塞项和下一步动作。它支持本地规则、LLM 和无模型降级三种路径，并完整保留原始笔记。

排练度量已经接入侧栏“排练度量”：按最近 7/30/90 天聚合已归档的排练次数、具体产出、亮点、阻塞、下一步、参与者和 Agent 路径，提供活动趋势、高频亮点/阻塞和最近记录。指标是确定性统计，不把有限反馈包装成未经证实的“排练质量分数”。

版本追踪已经接入侧栏“版本追踪”：选择两个已保存的剧本版本后，版本差异 Agent 会按场次编号对齐，标记新增/删除场次、角色和道具变化，以及带原始行号的新增、删除和修改台词；响应还会生成下游影响提醒，明确哪些排班、对词进度和资源结论需要人工复核。资源影响会进一步匹配当前用户近期的资源审计记录，并把场次、道具和审计记录一起带入资源复核入口。

舞台可视化已经接入侧栏“舞台可视化”：Stage Agent 会读取场景中的角色、道具、舞台提示和台词行号，生成角色头像调度地图，以及按原文顺序排列的上场、下场、走位、道具和台词事件。没有明确位置的对象会标记为待人工确认。

资源管理已经接入侧栏“资源管理”：可以独立维护道具/服装库存，预约排练室并拒绝同房间的时间重叠；选择剧本和场次后，Resource Agent 会逐项比较剧本道具需求与可用库存，输出“已就绪 / 维修中 / 缺失”及具体原因。资源变更 Agent 会保留库存、预约、配乐、预算和发票的结构化变更摘要；资源时间线支持按类型、变更动作和关键词筛选。剧本解析 Agent 会从明确的穿着/服装词中抽取服装需求，LLM 候选必须通过原文匹配，导演可在人工确认节点修正；调度 Agent 再把需求与服装库存快照对照，区分未匹配和库存不可用。

音乐与预算已经接入侧栏“音乐与预算”：可以记录配乐进入/转场/收尾的秒级时间轴笔记，维护预算项目和实际金额，登记发票元数据并关联预算项目。Resource Finance Agent 会分开统计预算、实际、发票和已核验金额，提示超支、待核验和未关联发票，不自动把发票当成已付款事实。

场记档案已经接入侧栏“场记档案”：场记可以独立记录导演指令、演员状态、走位、道具和声音变化，也可以关联剧本、场次和原文行号。Logbook Agent 会保留现场原话，只补充分类标签和可回看的剧本上下文，不会覆盖导演记录。

演员建议收件箱已经接入侧栏“建议收件箱”：演员可以提交表演、走位、剧本、协作和安全建议，导演可以在同一条记录上更新处理状态并留下回应。Suggestion Agent 只根据明确的安全、受伤、设备故障等词标记高优先级，不替演员改写建议内容。

知识资产已经接入侧栏“知识资产”：格言表会保留演员或导演提交的原文，只补充主题标签、剧本上下文和收藏状态；宣传文案 Agent 会根据作品名、场次标题、角色名和宣传 brief 生成标题、短文案、长文案与话题标签。生成支持 `auto`、`rules`、`llm` 三种模式，没有 API Key 或 LLM 调用失败时自动回退到本地规则，并在响应中说明依据，不虚构演出时间、地点或剧情。

剧本问答 RAG Agent 已接入侧栏“剧本问答”：它只在当前用户选中的剧本版本内检索场次上下文、台词和舞台提示，并为每条证据保留场次、来源类型、原文行号和匹配原因。规则检索不需要模型服务；可选语义检索需要 Embedding，回答组织可选 LLM。没有命中证据时，回答器会明确停止猜测。

Agent 运行记录已经接入侧栏“Agent运行记录”：剧本解析、调度草案、自动排班、对词、资源检查和剧本问答都会保存结构化摘要、运行模式、步骤 trace、耗时和降级原因；调度草案与自动排班还会通过 `parent_run_id` / `root_run_id` 组成可回看的运行链。页面额外聚合最近 30 天的失败率、降级率、按 Agent 统计和 failed step。LLM 调用只对连接超时、限流和 5xx 等可重试错误最多尝试 2 次，业务写入不自动重试。

Agent 评估集已经接入仓库：`evals/rehearsal_cases.json` 覆盖剧本解析、可行排班、调度工具调用链与父子 Run 关联、未排班原因与替代方案、资源状态、带证据/拒答的 RAG 路径、对词会话恢复，以及用确定性 mock provider 验证 LLM 结构化解析、原文锚定、角色语气、上下文记忆和适应性对词合同；`python -m evals.run_rehearsal_evals` 可以在没有真实模型服务的情况下输出逐项 JSON 报告，后端回归测试和 CI 会执行同一套评估。

演员可用时间现在作为独立的“演员时间池”保存，不要求先解析剧本；排班 Agent 在生成任务后读取这组可复用档期。工作台仍提供“预览调度（未确认）”入口，方便先观察结果，再决定是否进行人工确认。

前端侧栏目前聚焦剧团使用场景：`排练工作台`负责剧本解析与人工确认，`演员排练表`负责独立维护演员档期、生成场次任务和自动排班，`对词训练`负责逐句排练，`排练复盘`负责反馈归档，`排练度量`负责聚合进度信号，`场记档案`负责现场知识沉淀，`建议收件箱`负责演员意见流转，`知识资产`负责格言沉淀和宣传文案生成，`版本追踪`负责版本差异核对，`舞台可视化`负责走位和上下场核对，`资源管理`负责库存、排练室和排练前资源检查，`音乐与预算`负责配乐时间轴、预算和发票元数据。原项目的面试训练类入口已从主导航移除，相关旧路由暂时保留以避免破坏基础项目代码。

## Agent 能力路线

- 已完成：剧本解析、人工确认、版本追踪与带证据回指的 RAG 问答
- 已完成：排练调度、并行任务分组、演员时间池、自动排班、冲突优先级和候选替代方案
- 已完成：对词 Agent MVP、舞台可视化、资源检查、场记、复盘和建议收件箱
- 已完成：格言表与宣传文案 Agent，支持规则/LLM/降级路径
- 已完成：反馈度量面板，统计窗口、趋势、高频问题和 Agent 路径均可回溯
- 已完成：配乐时间轴、预算与发票元数据，以及预算/票据风险解释
- 已完成：核心 Agent 运行记录、步骤 trace、降级原因和用户隔离回看
- 已完成：GitHub Actions CI、Docker Compose 配置检查和面试演示材料收口
- 已完成：版本差异下游影响提醒，支持调度、对词和资源复核入口
- 已完成：资源变更审计、Agent 失败指标和有上限的 LLM 重试可观测性
- 已完成：资源审计与版本复核动作串联，资源时间线支持类型、变更动作和关键词筛选
- 已完成：无外部 API 依赖的 Agent 评估集，覆盖解析、排班、资源检查和 RAG 证据回指
- 已完成：调度 Agent 工具调用序列、参数/结果展示，以及对词 Agent 的持久化会话游标和 transcript
- 已完成：评估集覆盖调度工具调用链与对词会话恢复边界
- 已完成：调度草案与自动排班共享根 Run，并在 Agent运行记录页展示关联运行链
- 已完成：无共同档期时的分组/缩短/补档建议，以及导演人工覆盖排班
- 已完成：批量排班确认、原子写入和共享资源冲突校验
- 已完成：生成调度草案时读取配乐时间轴、预算、发票和服装库存快照，保留资源检查工具调用、预算/票据/服装风险 warning
- 已完成：从规则/LLM 原文中抽取服装需求，支持人工确认、原文行号、任务资源冲突和库存匹配 warning
- 待继续：补充更多真实剧本样本，并增加换装时间、服装跨场次冲突和借还状态等更细约束

## 技术栈

- Backend：Python、FastAPI、Pydantic、SQLite/文件存储
- Agent：显式状态编排、并行节点、结构化 LLM 输出、校验与降级
- RAG：剧本版本内的 `source_line` 证据检索，支持规则/可选语义与用户隔离
- Frontend：React、Vite、Tailwind CSS、Radix UI
- Deployment：Docker Compose

## 本地启动

```bash
copy .env.example .env
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

示例剧本位于 [`docs/examples/qidian-demo-script.md`](docs/examples/qidian-demo-script.md) 和 [`docs/examples/qidian-echo-room-script.md`](docs/examples/qidian-echo-room-script.md)。
演员档期示例位于 [`docs/examples/qidian-actor-availability.csv`](docs/examples/qidian-actor-availability.csv)。
完整演示步骤、面试讲解话术和提交前验证清单位于 [`docs/demo-and-interview.md`](docs/demo-and-interview.md)。
Agent 评估集说明和面试讲解要点位于 [`docs/agent-evaluation.md`](docs/agent-evaluation.md)。
完整环境变量、Docker 和线上安全注意事项见 [`docs/deployment.md`](docs/deployment.md)。
提交到 GitHub 后，`.github/workflows/ci.yml` 会自动执行后端回归、前端类型/单测/lint/build 和 Docker Compose 配置检查。

## 第一阶段 API

需要先登录取得 Bearer Token：

- `POST /api/rehearsal/scripts/parse`：解析 JSON 中的 `title`、`version_label`、`script_text`；可选 `analysis_mode`：`auto`、`rules`、`llm`
- `POST /api/rehearsal/scripts/parse-file`：解析 `.txt`、`.md`、`.markdown` 或可提取文本的 `.pdf`；可选查询参数 `analysis_mode`
- `GET /api/rehearsal/scripts`：列出当前用户的剧本解析结果
- `GET /api/rehearsal/scripts/{script_id}`：读取单个解析结果
- `PUT /api/rehearsal/scripts/{script_id}/review`：提交人工确认或场次元数据修改
- `GET /api/rehearsal/availability`：读取当前用户的演员时间池
- `PUT /api/rehearsal/availability`：保存或替换当前用户的演员时间池
- `POST /api/rehearsal/scripts/{script_id}/schedule/draft`：生成排练调度草案；请求体可传 `{"default_minutes": 45, "preview": true}` 生成未确认预览
- `GET /api/rehearsal/scripts/{script_id}/schedule`：读取最近一次调度草案
- `POST /api/rehearsal/scripts/{script_id}/schedule/plan`：根据演员可用时间生成自动排班结果
- `POST /api/rehearsal/scripts/{script_id}/schedule/override`：保存导演确认的单个人工覆盖时段；可选 `room_name` 会触发排练室预约检查，并保留审计轨迹
- `POST /api/rehearsal/scripts/{script_id}/schedule/override-batch`：原子确认多个排班时段；任一任务无效、已人工确认、排练室不可用或与共享演员/道具冲突时整批拒绝，不产生半成品
- `POST /api/rehearsal/scripts/{script_id}/line-reading`：推进一轮角色对词；支持 `strict` 和 `adaptive` 模式
- `GET /api/rehearsal/scripts/{script_id}/line-reading/sessions/{session_id}`：恢复当前用户的对词游标、transcript 和下一句原词
- `POST /api/rehearsal/scripts/{script_id}/rag`：在当前剧本版本内检索证据并回答问题；支持 `rules`/`semantic` 检索和 `auto`/`rules`/`llm` 回答
- `GET /api/rehearsal/agent-runs?limit=50`：读取当前用户最近的 Agent 运行摘要和结构化 trace
- `GET /api/rehearsal/agent-runs/{run_id}`：读取单次 Agent 运行详情
- `POST /api/rehearsal/feedback`：归档一次排练反馈并生成镜像总结；可不关联剧本
- `GET /api/rehearsal/feedback`：读取当前用户的排练反馈档案
- `GET /api/rehearsal/feedback/metrics?days=30`：统计当前用户在窗口内的排练产出、阻塞、下一步和 Agent 路径
- `GET /api/rehearsal/feedback/{record_id}`：读取单条反馈档案
- `POST /api/rehearsal/scripts/{script_id}/diff`：将目标版本与请求体中的 `compare_script_id` 做结构化差异比较，并匹配当前用户的相关资源审计记录
- `GET /api/rehearsal/scripts/{script_id}/stage/{scene_id}`：生成单个场次的舞台地图和动态事件
- `GET/PUT /api/rehearsal/resources/inventory`：读取或替换当前用户的道具/服装库存
- `GET /api/rehearsal/resources/audit?limit=50&resource_type=inventory&change_type=updated&query=椅子`：读取并筛选资源变更审计
- `GET /api/rehearsal/resources/rooms`：读取当前用户的排练室预约
- `POST /api/rehearsal/resources/rooms`：创建排练室预约；同房间同日期的重叠时间返回 `409`
- `DELETE /api/rehearsal/resources/rooms/{booking_id}`：取消排练室预约
- `POST /api/rehearsal/scripts/{script_id}/resources/check`：按剧本或单场检查道具库存就绪情况
- `GET/PUT /api/rehearsal/resources/music`：读取或替换配乐时间轴笔记
- `GET/PUT /api/rehearsal/resources/budget`：读取或替换制作预算项目
- `GET/PUT /api/rehearsal/resources/invoices`：读取或替换发票元数据
- `GET /api/rehearsal/resources/finance-summary`：返回预算、实际、发票关联和风险提示汇总
- `POST /api/rehearsal/logbook`：归档一条场记，可选关联剧本、场次和原文行号
- `GET /api/rehearsal/logbook`：读取当前用户的场记档案
- `DELETE /api/rehearsal/logbook/{log_id}`：删除一条场记记录
- `POST /api/rehearsal/suggestions`：提交一条演员建议，可选关联剧本和场次
- `GET /api/rehearsal/suggestions`：读取当前用户的建议收件箱
- `PATCH /api/rehearsal/suggestions/{suggestion_id}`：更新建议状态和导演回应
- `DELETE /api/rehearsal/suggestions/{suggestion_id}`：删除一条建议
- `POST /api/rehearsal/knowledge/mottos`：保存一条格言，可选关联剧本和场次
- `GET /api/rehearsal/knowledge/mottos`：读取当前用户的格言表
- `PATCH /api/rehearsal/knowledge/mottos/{motto_id}`：更新格言收藏状态
- `DELETE /api/rehearsal/knowledge/mottos/{motto_id}`：删除一条格言
- `POST /api/rehearsal/knowledge/promo`：根据作品信息和可选剧本结构生成并保存宣传文案
- `GET /api/rehearsal/knowledge/promo`：读取当前用户的历史宣传文案

## 基础项目与许可

本项目基于 [AnnaSuSu/TechSpar](https://github.com/AnnaSuSu/TechSpar) 的干净 Python/FastAPI 历史基线建立，保留其原始 [CC BY-NC 4.0](LICENSE) 许可与致谢信息，并在此基础上进行话剧排练领域的增删改。新代码和文档的改动以本仓库提交记录为准。

请勿将 `.env`、`data/users/`、个人剧本、API Key 或其他运行时数据提交到公开仓库。

## 项目仓库

[github.com/cartonmouse/qidian-rehearsal-agent](https://github.com/cartonmouse/qidian-rehearsal-agent)
