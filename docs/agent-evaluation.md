# Agent 评估集

`evals/rehearsal_cases.json` 是奇点排练 Agent 的第一版离线评估集。它不依赖 LLM、Embedding 或登录态，适合本地开发、CI 和面试演示，目标是验证 Agent 的可观察行为是否稳定，而不是用一个未经定义的分数评价“生成得像不像人”。

## 覆盖范围

当前包含 9 个用例：

| 用例 | 验证内容 |
| --- | --- |
| `script-analysis-basic` | 场次、角色、道具、trace 和原文行号是否完整 |
| `schedule-feasible` | 已确认剧本能生成任务，并按共享演员资源拆分并行组、连续排班；草案 Run 与排班 Run 保留父子关系 |
| `schedule-unassigned` | 演员没有共同时间时，任务标记为未排班、给出冲突优先级，并提供分组排练等候选方案 |
| `schedule-missing-availability` | 缺少演员档期时，任务说明缺失角色，并提供补充档期方案 |
| `resource-check-scene` | 道具库存的已就绪、维修中、缺失状态和解释是否正确 |
| `rag-evidence-and-no-hallucination` | RAG 是否返回带原文行号的证据，且回答引用证据 ID |
| `rag-empty-stops-guessing` | 没有证据时是否明确停止猜测 |
| `line-reading-session-resume` | 对词会话是否保存游标、transcript，并拒绝客户端跳跃进度 |
| `llm-contract-source-and-adaptive` | 用确定性 mock provider 验证 LLM 结构化解析、原文锚定和适应性对词响应 |

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

后续扩展方向是把更多真实剧本样本纳入评估，并为调度 Agent 的真实工具调用和多轮对词记忆增加同样的合同测试。
