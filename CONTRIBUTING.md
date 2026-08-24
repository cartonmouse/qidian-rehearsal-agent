# 参与贡献

感谢你为奇点排练 Agent 提交问题、改进建议或代码。项目围绕剧本解析、排练调度、对词、舞台可视化和排练资产协作持续演进。

## 开始之前

- 小改动（修复问题、补充文档、界面优化）可以直接提交 Issue 或 Pull Request。
- 新 Agent、数据模型或部署方式等较大改动，建议先在 Issue 中说明场景、边界和验收方式。
- 请不要提交真实剧本、演员个人信息、API Key、`.env` 或运行时 `data/`。

## 本地开发

完整步骤见 [部署说明](docs/deployment.md)。常用命令：

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 18000

cd frontend
npm install
npm run dev
```

模型服务可以在登录后的设置页按用户配置；规则解析、排班和原词对词不依赖外部模型。

## 项目结构

```text
backend/rehearsal/   剧本、调度、RAG、对词和舞台领域服务
backend/routers/     FastAPI 路由
backend/storage/     用户隔离数据与运行记录
frontend/src/        React + TypeScript 页面与组件
evals/               离线 Agent 评估案例
docs/                产品、开发、部署和评估说明
tests/               回归测试
```

## 代码约定

- 路由按领域拆分，鉴权统一使用当前用户依赖。
- LLM 输出必须经过结构化解析和来源校验；原文、档期和资源约束由确定性逻辑守门。
- 新增 Agent 能力时，同时补充工具调用记录、失败回退和离线评估用例。
- 前端改动后运行 `npm run typecheck`、`npm run lint` 和 `npm run build`。
- 后端改动后运行 `python -m compileall -q backend` 和相关回归测试。

## 提交与 Pull Request

- 提交信息使用 `类型(范围): 描述`，例如 `feat(schedule): explain unassigned reasons`。
- 一个提交尽量只解决一个问题。
- PR 请说明动机、实现范围、验证命令；涉及界面变化时附上截图。

## 许可

项目整体遵循 [CC BY-NC 4.0](LICENSE)。部分通用前端组件保留其原始目录中的许可说明，贡献前请一并阅读对应 `LICENSE` 文件。
