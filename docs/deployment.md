# 部署说明

这页只写当前仓库真实可用的启动方式。

### 环境要求

* Python `3.11+`
* Node.js `18+`
* LLM 和 Embedding **不是奇点排练规则分支的启动前置条件**；只有启用 LLM 适应性能力、语义检索、LLM 组织式剧本问答或原项目面试能力时才需要配置

录音上传转写不是必需功能；如果你要用它，再额外配置语音相关环境变量。

### 1. 复制环境变量

```bash
cp .env.example .env
```

### 2. 最小可运行配置

如果目标是先运行奇点排练的规则分支，只需要完成 `.env`、依赖和默认账号配置即可，不必填写 LLM 或 Embedding API。剧本解析、人工确认、规则检索式剧本问答、调度、排班、原词对词、舞台可视化、资源检查、音乐时间轴、预算、发票、场记、复盘、度量、建议收件箱和知识资产的规则路径都可以直接使用。

如果要启用适应性对词、LLM 复盘、LLM 宣传文案、语义检索式剧本问答、LLM 组织式剧本问答，或原项目的 RAG/面试能力，再配置一套 **OpenAI 兼容 LLM 接口** 和/或 Embedding。使用远程 Embedding API 时，配置如下：

```env
API_BASE=https://your-llm-api-base/v1
API_KEY=sk-your-api-key
MODEL=your-model-name
EMBEDDING_BACKEND=api
EMBEDDING_API_BASE=https://your-embedding-api-base/v1
EMBEDDING_API_KEY=sk-your-embedding-key
EMBEDDING_API_MODEL=your-embedding-model
```

这些变量分别是：

* `API_BASE`：主 LLM 的 OpenAI 兼容接口地址。面试、复盘、宣传文案、适应性对词和剧本问答的 LLM 组织分支都会走它。
* `API_KEY`：上面这个 LLM 接口的密钥。
* `MODEL`：主 LLM 模型名。
* `EMBEDDING_BACKEND`：Embedding 走哪条路，只能是 `api` 或 `local`。
* `EMBEDDING_API_BASE`：Embedding 接口地址。如果你用官方 OpenAI Embedding，这个值可以留空。
* `EMBEDDING_API_KEY`：Embedding 接口密钥。
* `EMBEDDING_API_MODEL`：Embedding 模型名。这里不要照抄示例，应该改成你的服务实际支持的模型。

如果你只是想先把项目跑起来，不一定要先购买模型服务。一个简单的免费示例是：

* 主 LLM：ModelScope 的 `ZhipuAI/GLM-5`
* Embedding：SiliconFlow 的 `BAAI/bge-large-zh-v1.5`

注册入口：

* ModelScope: <https://modelscope.cn/home>
* SiliconFlow: <https://cloud.siliconflow.cn/>

配置示例：

```env
API_BASE=https://api-inference.modelscope.cn/v1
API_KEY=your-modelscope-sdk-token
MODEL=ZhipuAI/GLM-5

EMBEDDING_BACKEND=api
EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=sk-your-siliconflow-key
EMBEDDING_API_MODEL=BAAI/bge-large-zh-v1.5
```

`API_KEY` 填 ModelScope 的 SDK Token，`EMBEDDING_API_KEY` 填 SiliconFlow 的 API Key。主 LLM 和 Embedding 可以分开用不同服务商，不需要来自同一家。

默认认证配置如下；如果不改，启动后可以直接登录：

```env
DEFAULT_EMAIL=admin@techspar.local
DEFAULT_PASSWORD=admin123
ALLOW_REGISTRATION=false
```

### 3. 如果你想用本地 Embedding

如果你不想走远程 Embedding API，可以改成：

```env
EMBEDDING_BACKEND=local
LOCAL_EMBEDDING_MODEL=BAAI/bge-m3
LOCAL_EMBEDDING_PATH=
```

说明：

* `LOCAL_EMBEDDING_MODEL`：本地 Embedding 模型名。
* `LOCAL_EMBEDDING_PATH`：如果你已经把模型下载到本地，可以直接写本地路径。
* `LOCAL_EMBEDDING_MODEL` 和 `LOCAL_EMBEDDING_PATH` 二选一即可。
* 本地模式需要额外安装依赖：`pip install -r requirements.local-embedding.txt`

### 4. 本地手动启动

后端：

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

启动后访问：

```text
http://localhost:5173
```

如果本机已经有旧的前端或后端进程占用默认端口，必须让前端代理明确指向同一份代码启动的后端，避免出现“解析成功但页面报 `undefined.length`”这类版本错配。可以使用一组隔离端口：

```powershell
# 终端一：后端
uvicorn backend.main:app --host 127.0.0.1 --port 8001

# 终端二：前端（在仓库根目录执行）
$env:TECHSPAR_API_TARGET = "http://127.0.0.1:8001"
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5181
```

打开 `http://127.0.0.1:5181` 后，若仍提示结构字段缺失，先检查 `http://127.0.0.1:8001/openapi.json` 是否来自当前仓库，再清理旧的 Vite 页面或切换到上述隔离端口。前端会对缺少的数组字段做安全归一化，并在剧本解读结果中保留版本错配提醒；这只是兼容旧服务的保护，不会替代后端升级。

### 5. Docker 启动

```bash
docker compose up --build
```

启动后访问：

```text
http://localhost
```

### 6. 面试 Copilot 的额外配置

如果你要启用 Copilot 的独立模型、实时语音识别或联网公司搜索，还需要补齐这些可选项：

```env
COPILOT_API_BASE=
COPILOT_API_KEY=
COPILOT_MODEL=
DASHSCOPE_API_KEY=
TAVILY_API_KEY=
```

这些变量的作用分别是：

* `COPILOT_API_BASE` / `COPILOT_API_KEY` / `COPILOT_MODEL`：给 Copilot 单独指定一套 OpenAI 兼容模型配置。不填时会回退到主 LLM。
* `DASHSCOPE_API_KEY`：给 Copilot 的**实时语音识别**使用（模型 `qwen3-asr-flash-realtime`，走 OpenAI Realtime 兼容 WebSocket 协议，自带服务端 VAD）。同一个 key 也承担"录音上传批量转写"用途。不配时，Copilot 仍可用，但只能手动输入 HR 的问题。
* `TAVILY_API_KEY`：给 Copilot Prep 阶段的**公司联网搜索**使用。不配时不会整段报废，但公司情报会退化成"跳过联网搜索"。

如果你还想让 Copilot **自动区分 HR 与候选人**（无需手动按钮切换），再补上腾讯云 VPR 声纹识别（可选）：

```env
TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
TENCENT_VPR_APP_ID=
```

配好后进入 Copilot 设置页的"声纹识别（可选）"卡片录制 6-15 秒候选人语音完成注册，实时面试就会自动打角色标签。不配置时一切功能照旧，只是角色需要手动切换。

额外注意：

* 如果你只是想先用 Copilot，看 JD 分析、匹配分析和策略树，`DASHSCOPE_API_KEY`、`TAVILY_API_KEY`、`TENCENT_*` 都不是强制项。
* 这些值怎么申请、控制台里去哪里找，统一看 [外部服务配置](external-services.md)。

### 7. 录音转写的额外配置

语音转写现在拆成两条链路，需要配什么取决于你要开哪一条：

**短音频（答题时语音输入、几秒~几分钟）**

只需要 `DASHSCOPE_API_KEY`，不需要任何对象存储。走 DashScope 同步 `chat/completions`，base64 直传。

```env
DASHSCOPE_API_KEY=
```

> 留空时若 `COPILOT_API_KEY` 指向 `https://dashscope.aliyuncs.com/compatible-mode/v1`，会自动复用那个 key，避免一套 DashScope 账号配两次。

**长音频（录音复盘上传整段面试录音，可能几十分钟）**

除了上面那个 key，还要补齐阿里云 OSS。走 `qwen3-asr-flash-filetrans` 异步接口，它只接受公网 URL，所以必须先把音频传上 OSS 拿到签名 URL：

```env
ALIYUN_OSS_ACCESS_KEY_ID=
ALIYUN_OSS_ACCESS_KEY_SECRET=
ALIYUN_OSS_BUCKET=
ALIYUN_OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com
```

* `ALIYUN_OSS_ACCESS_KEY_ID` / `SECRET`：阿里云 RAM 子账号（或主账号）AK/SK。
* `ALIYUN_OSS_BUCKET`：目标 OSS 存储桶名。桶**可以保持私有**，代码里用 1 小时过期的签名 URL 让 DashScope 拉文件，无需公开读。
* `ALIYUN_OSS_ENDPOINT`：桶所在区域的 endpoint，如 `oss-cn-shanghai.aliyuncs.com` / `oss-cn-beijing.aliyuncs.com`。

如果这些都没配，也不影响主要训练流程 —— 录音复盘可以直接粘贴逐字稿文本。

这些值怎么申请、控制台里去哪里找，统一看 [外部服务配置](external-services.md)。

### 8. 线上部署注意事项

* 手动开发模式下，前端默认是 `5173`，后端是 `8000`。
* Docker 模式下，前端默认对外暴露 `80` 端口。
* 如果你在线上要使用麦克风或录音相关能力，建议启用 HTTPS；浏览器对非 `localhost` 的音频权限更严格。
* 线上环境不要保留默认的 `JWT_SECRET`、`DEFAULT_PASSWORD`。

### 9. GitHub → Render 面试演示部署

仓库根目录的 `render.yaml` 和 `deploy/Dockerfile` 已准备好一个前后端合一的公开演示服务：Nginx 提供 React 页面，同时把 `/api` 和 `/ws` 反向代理到 FastAPI。这样不需要额外配置前端 API 地址，适合面试演示。

操作步骤：

1. 将仓库推送到 GitHub，并确认 `main` 分支包含 `render.yaml`。
2. 在 Render 中选择 **New → Blueprint**，连接 GitHub 仓库并选择 `render.yaml`。
3. 创建服务后等待构建完成，Render 会分配一个 `onrender.com` 访问地址。
4. 打开该地址注册演示账号；规则解析、人工确认、调度、排班、原词对词和资源管理不要求填写 LLM/Embedding API。
5. 如果要演示适应性对词、LLM 剧本问答或语义检索，再在登录后的设置页填写自己的模型服务。不要把 API Key 写进仓库或 `render.yaml`。

这是面试演示配置：`ALLOW_REGISTRATION=true` 便于评委直接注册，JWT 密钥和默认密码由托管平台生成。免费实例的本地文件系统可能在重启或休眠后重置，因此不要上传真实剧本或个人资料；需要长期保存数据时，应改用带持久磁盘/数据库的付费部署方案。

当前仓库只提供可复现的托管配置，不把“已生成 Render 网址”冒充成已上线；必须在 Render 账户中完成一次 Blueprint 创建后才会产生真实网址。

### 10. GitHub CI

仓库中的 `.github/workflows/ci.yml` 会在 `main`/`master` 推送和 Pull Request 上执行：

* 后端依赖安装、`compileall` 和排练 Agent 回归；
* 前端 `typecheck`、单元测试、lint 和生产构建；
* 使用 `.env.example` 的 Docker Compose 静态配置检查。

CI 不需要任何 LLM、Embedding 或语音服务密钥；排练规则分支和测试数据均在本地确定性运行。
