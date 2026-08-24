# 奇点排练 Agent 文档中心

文档围绕话剧排练场景组织，描述当前仓库真实实现，不包含个人资料或私人运行数据。

## 推荐阅读顺序

1. [部署说明](deployment.md)：本地、Docker 和公开演示部署。
2. [排练 Agent 设计说明](rehearsal-agent.md)：领域模型、流程边界和人工确认节点。
3. [Agent 评估集](agent-evaluation.md)：离线评估案例、工具调用和边界校验。
4. [开发者说明](developer.md)：目录结构、开发命令和贡献约定。
5. [外部服务配置](external-services.md)：LLM、Embedding 和本地模型配置。

## 示例

- [《轨道之外》排练示例](examples/qidian-demo-script.md)
- [《回声室》排练示例](examples/qidian-echo-room-script.md)
- [可排班演员档期](examples/qidian-actor-availability-feasible.csv)
- [无共同时间的冲突档期](examples/qidian-actor-availability.csv)

文档中的剧本、角色、档期和资源均为示例数据。请勿把真实剧本、演员联系方式或模型密钥提交到仓库。
