# 外部服务配置

这页只说明奇点排练 Agent 的可选模型、检索和音频服务：如何填写配置、如何验证连通，以及没有配置时系统如何降级。项目的规则解析、人工确认、调度、排班、原词对词和舞台可视化不依赖外部 API。

如果你只是想先把项目跑起来，这页不是必读；先看 [部署说明](deployment.md)。

### 先看总表

| 环境变量 | 用在哪里 | 不配置会怎样 |
| --- | --- | --- |
| `API_BASE` `API_KEY` `MODEL` | 适应性对词、LLM 剧本问答、复盘和宣传文案 | 对应功能降级到规则路径或不可用 |
| `EMBEDDING_BACKEND` `EMBEDDING_API_*` | 语义检索式剧本问答 | 可使用规则检索；语义检索不可用 |
| `LOCAL_EMBEDDING_MODEL` `LOCAL_EMBEDDING_PATH` | 本地 Embedding 模型 | 需要安装本地依赖并下载模型后才能使用 |
| `DASHSCOPE_API_KEY` | 可选语音输入和音频转写 | 只能使用文本输入 |
| `ALIYUN_OSS_*` | 长音频转写的临时文件存储 | 短音频可用，长音频转写不可用 |

所有密钥都应通过登录后的设置页或部署环境变量提供，不能提交到 Git。每个用户的模型配置独立保存，服务端不会把一个用户的 API Key 展示给其他用户。

---

### 1. 主 LLM 配置

奇点使用 OpenAI 兼容的 Chat Completions 接口。配置主 LLM 后，可启用适应性对词、LLM 组织式剧本问答、复盘摘要和宣传文案；连接失败或返回格式不符合结构化约束时，Agent 会返回规则降级结果和可解释的引擎标记。

```env
API_BASE=https://your-llm-api-base/v1
API_KEY=sk-your-api-key
MODEL=your-model-name
```

`API_BASE` 是否包含 `/v1` 以供应商文档为准，`MODEL` 必须填写账号实际可调用的模型 ID。主 LLM 可以使用任意 OpenAI 兼容服务，不要求和 Embedding 使用同一家供应商。

#### 如何验证

1. 在供应商控制台确认 API Key 和模型已开通。
2. 使用供应商提供的最小 Chat Completions 请求验证连通。
3. 将配置填入设置页，运行一次适应性对词或剧本问答。
4. 在 Agent 运行记录中确认 `engine`、耗时和降级原因。

如果供应商支持 `/models`，也可以先运行：

```bash
curl "$API_BASE/models" \
  -H "Authorization: Bearer $API_KEY"
```

---

### 2. Embedding 配置

Embedding 用于剧本、个人资料库和记忆的向量化。奇点支持远程 API 和本地 Hugging Face 模型两种模式。

#### 远程 Embedding API

```env
EMBEDDING_BACKEND=api
EMBEDDING_API_BASE=https://your-embedding-api-base/v1
EMBEDDING_API_KEY=sk-your-embedding-key
EMBEDDING_API_MODEL=your-embedding-model
```

#### 本地 Embedding 模型

```env
EMBEDDING_BACKEND=local
LOCAL_EMBEDDING_MODEL=BAAI/bge-m3
LOCAL_EMBEDDING_PATH=
```

本地模式需要先安装额外依赖：

```bash
pip install -r requirements.local-embedding.txt
```

`LOCAL_EMBEDDING_PATH` 可以填写已经下载好的模型目录；留空时，程序会按模型名加载或下载。离线部署时应填写本地路径，并提前把模型放入服务器。

---

### 3. DashScope 音频服务（可选）

需要语音输入或音频转写时配置阿里云百炼的 API Key：

```env
DASHSCOPE_API_KEY=sk-your-dashscope-key
```

短音频走同步接口，直接传输音频内容，不依赖对象存储。长音频转写使用异步接口，需要同时配置下一节的 OSS。没有该 Key 时，文本输入和规则排练功能不受影响。

官方入口：

* 百炼 API Key 说明：<https://help.aliyun.com/zh/model-studio/get-api-key>
* 百炼控制台：<https://bailian.console.aliyun.com/>

---

### 4. 阿里云 OSS（长音频可选）

长音频转写的服务端协议需要公网可访问的临时 URL，因此先把文件上传到 OSS，再把短期签名 URL 交给转写服务：

```env
ALIYUN_OSS_ACCESS_KEY_ID=
ALIYUN_OSS_ACCESS_KEY_SECRET=
ALIYUN_OSS_BUCKET=
ALIYUN_OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com
```

建议使用 RAM 子账号和最小 bucket 级权限。Bucket 可以保持私有，代码只生成短期签名 URL，不需要开启公开读权限。`ALIYUN_OSS_ENDPOINT` 不要带 `https://`，并且必须和 Bucket 所在地域一致。

控制台入口：

* 阿里云 OSS 控制台：<https://oss.console.aliyun.com/>
* 阿里云 RAM 访问控制：<https://ram.console.aliyun.com/>

如果看到 `Alibaba OSS not configured`、`AccessDenied` 或 `NoSuchBucket`，依次检查变量是否完整、Bucket 名称、Endpoint 地域和 RAM 权限。

---

### 推荐配置顺序

1. 先不配置任何外部服务，验证规则解析、人工确认、调度和排班闭环。
2. 配置 Embedding，验证剧本问答的检索证据和原文行号。
3. 配置主 LLM，验证适应性对词、LLM 问答或宣传文案的结构化输出。
4. 需要语音输入时再配置 `DASHSCOPE_API_KEY`；只有长音频才额外配置 `ALIYUN_OSS_*`。

---

### 安全边界

* `.env`、部署平台密钥和登录后保存的模型配置都不应提交到仓库。
* 示例文件只放占位符，不放真实 API Key、账号密码、剧本原文或个人资料。
* 公开实例使用临时测试数据；需要长期保存剧本和排练资产时，配置持久化磁盘或数据库。
* 发现密钥曾经进入 Git 历史时，应立即在供应商控制台撤销并重新生成。普通提交删除不会清除 Git 历史，需要单独进行历史清理。
