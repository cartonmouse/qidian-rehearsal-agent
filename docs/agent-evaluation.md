# Agent 评估集

`evals/rehearsal_cases.json` 是奇点排练 Agent 的第一版离线评估集。它不依赖 LLM、Embedding 或登录态，适合本地开发、CI 和面试演示，目标是验证 Agent 的可观察行为是否稳定，而不是用一个未经定义的分数评价“生成得像不像人”。

## 覆盖范围

当前包含 16 个用例：

| 用例 | 验证内容 |
| --- | --- |
| `script-analysis-basic` | 场次、角色、道具、trace 和原文行号是否完整 |
| `script-analysis-echo-room` | 第二份原创双场剧本的场次、角色、道具、服装需求和来源行号是否稳定 |
| `schedule-feasible` | 已确认剧本能生成任务，并按共享演员资源拆分并行组、连续排班；同时验证工具阶段顺序、结果字段契约、草案 Run/排班 Run 父子关系，以及批量确认的成功、共享资源冲突和重复任务拒绝 |
| `schedule-cross-date-resource` | 共享演员/道具/服装在同一日期仍需串行；跨日期批量确认可以并行落位，验证排练室工具检查，以及配乐/预算/发票/剧本服装需求/服装库存资源快照和财务/库存风险 warning |
| `schedule-costume-capacity` | 同名服装库存为 2 件时允许两个场次并行，并在资源快照、工具结果和排班任务中保留容量合同 |
| `schedule-costume-occupancy` | 同名服装只有 1 件时，两个不同演员的场次自动错开；验证资源容量阻塞原因和排班工具参数合同 |
| `schedule-costume-changeover` | 同一演员前后场次服装变化时，自动排班预留 10 分钟换装缓冲；同服装不额外占用时间，档期不足和批量确认冲突均给出可解释原因 |
| `version-costume-resource-impact` | 版本差异识别新增/移除服装，生成资源复核影响，并保留服装清单作为下游输入 |
| `costume-custody-capacity` | 借出/归还动作、多人持有人分配、`custody_id` 定向归还、审计操作合同、超额归还边界、逾期提醒，以及借出后服装容量扣除和归还后恢复 |
| `schedule-unassigned` | 演员没有共同时间时，任务标记为未排班、给出冲突优先级，并提供分组排练等候选方案 |
| `schedule-missing-availability` | 缺少演员档期时，任务说明缺失角色，并提供补充档期方案 |
| `resource-check-scene` | 道具库存的已就绪、维修中、缺失状态和解释是否正确 |
| `rag-evidence-and-no-hallucination` | RAG 是否返回带原文行号的证据，且回答引用证据 ID |
| `rag-empty-stops-guessing` | 没有证据时是否明确停止猜测 |
| `line-reading-session-resume` | 对词会话是否保存游标、transcript，并拒绝客户端跳跃进度 |
| `llm-contract-source-and-adaptive` | 用确定性 mock provider 验证 LLM 结构化解析、原文锚定、角色语气/排练上下文、适应性对词响应和多轮会话恢复 |

评估结果按“用例通过率”汇总，同时保留每个检查项的实际值和预期值。失败时会记录具体用例、检查项和异常，便于定位是解析回归、排班边界变化，还是证据回指丢失。

## 运行方式

在仓库根目录执行：

```bash
python -m evals.run_rehearsal_evals
```

命令会输出一份 JSON 报告；所有用例通过时退出码为 `0`，任意用例失败时退出码为 `1`。后端回归测试也会调用同一个 `evaluate_cases()`，因此评估集会随 GitHub Actions 一起运行。

## 面试讲解要点

这组评估体现了 Agent 工程中的三个原则：

1. 先定义可观察的结构化契约，再讨论模型回答质量；例如排班必须给出状态和未排班原因，RAG 必须带 `source_line`。
2. 把正常路径、边界路径和拒答路径放进同一套回归；“没有共同时间”和“没有证据”不是异常，而是产品必须解释的结果。
3. 评估集不绑定供应商 API。规则路径可在 CI 中稳定运行，LLM 路径用确定性 mock provider 验证结构化合同，真实供应商只负责运行时生成。

后续扩展方向是把更多真实排练样本纳入评估，并继续加入真实演出流程和更复杂的剧本版本变化组合样本。
