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
并行提取角色、台词、道具
        ↓
校验与保守修复
        ↓
按用户隔离保存结构化排练数据
```

当前接口会返回每个场次、角色、台词、道具和 Agent trace，并为台词与场次保留原剧本行号，方便导演人工核对。第一阶段使用本地可解释解析器，因此没有配置模型服务也能运行；后续会在相同的状态契约中加入 LLM 结构化抽取、人工确认和 RAG 证据链。

## 计划中的 Agent 能力

- 剧本解读：版本追踪、分场、角色和道具抽取、RAG 问答
- 排练调度：演员可用时间确认、场次排班、并行排练任务
- 对词 Agent：按角色对词、上下文记忆和适应性改写
- 知识资产：场记、导演反馈、建议收件箱、宣传文案
- 舞台可视化：角色、道具、上下场和调度地图
- 资源管理：道具、服装、音乐、预算和排练室
- 反馈度量：每次排练产出、反馈归档和进度指标

## 技术栈

- Backend：Python、FastAPI、Pydantic、SQLite/文件存储
- Agent：显式状态编排，逐步接入 LangGraph 与结构化 LLM 输出
- RAG：沿用基础项目的用户隔离知识库和向量检索能力
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

示例剧本位于 [`docs/examples/qidian-demo-script.md`](docs/examples/qidian-demo-script.md)。

## 第一阶段 API

需要先登录取得 Bearer Token：

- `POST /api/rehearsal/scripts/parse`：解析 JSON 中的 `title`、`version_label`、`script_text`
- `POST /api/rehearsal/scripts/parse-file`：解析 `.txt`、`.md`、`.markdown` 或可提取文本的 `.pdf`
- `GET /api/rehearsal/scripts`：列出当前用户的剧本解析结果
- `GET /api/rehearsal/scripts/{script_id}`：读取单个解析结果

## 基础项目与许可

本项目基于 [AnnaSuSu/TechSpar](https://github.com/AnnaSuSu/TechSpar) 的干净 Python/FastAPI 历史基线建立，保留其原始 [CC BY-NC 4.0](LICENSE) 许可与致谢信息，并在此基础上进行话剧排练领域的增删改。新代码和文档的改动以本仓库提交记录为准。

请勿将 `.env`、`data/users/`、个人剧本、API Key 或其他运行时数据提交到公开仓库。

## 项目仓库

[github.com/cartonmouse/qidian-rehearsal-agent](https://github.com/cartonmouse/qidian-rehearsal-agent)
