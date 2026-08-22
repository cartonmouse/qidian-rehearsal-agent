---
status: accepted
---
# 从 TechSpar 的 Python 基线建立独立项目

奇点排练 Agent 采用 TechSpar 的干净 Python/FastAPI 历史提交作为工程基线，在新仓库中保留其 React/Vite 前端壳、认证、LLM 配置、RAG、SQLite 和通用 UI；面试领域页面暂时作为 legacy 保留，逐步由排练领域功能替换。这样既能复用已经验证过的平台能力，也能让新仓库的公开内容只围绕话剧排练展开，并避免把本地简历、密钥和运行数据带入版本库。

## Considered Options

- 直接修改原 TechSpar 仓库：会把两个产品的业务边界混在一起，也会影响原仓库的未提交本地修改。
- 从当前 TypeScript 主线重新开始：会丢失当前 Python/FastAPI 版本中已经可复用的后端能力。
- 使用干净 Python 历史提交建立衍生仓库：保留复用价值，同时明确新产品边界。
