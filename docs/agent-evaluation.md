# Agent 评估集

`evals/rehearsal_cases.json` 是奇点排练 Agent 的第一版离线评估集。它不依赖 LLM、Embedding 或登录态，适合本地开发、CI 和面试演示，目标是验证 Agent 的可观察行为是否稳定，而不是用一个未经定义的分数评价“生成得像不像人”。

## 覆盖范围

当前包含 7 个用例：

| 用例 | 验证内容 |
| --- | --- |
| `script-analysis-basic` | 场次、角色、道具、trace 和原文行号是否完整 |
| `schedule-feasible` | 已确认剧本能生成任务，并按共享演员资源拆分并行组、连续排班 |
| `schedule-unassigned` | 演员没有共同时间时，任务标记为未排班并给出具体原因 |
| `resource-check-scene` | 道具库存的已就绪、维修中、缺失状态和解释是否正确 |
| `rag-evidence-and-no-hallucination` | RAG 是否返回带原文行号的证据，且回答引用证据 ID |
| `rag-empty-stops-guessing` | 没有证据时是否明确停止猜测 |
| `line-reading-session-resume` | 对词会话是否保存游标、transcript，并拒绝客户端跳跃进度 |

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
3. 评估集不绑定供应商 API。规则路径可在 CI 中稳定运行，LLM 路径可以在后续增加带 mock provider 的合同测试和离线样本评估。

后续扩展方向是加入人工确认修改、版本差异下游影响、资源审计匹配和适应性对词的 mock provider 合同测试，并把更多 Agent 之间的运行轨迹关联纳入评估断言。
