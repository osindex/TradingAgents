# TradingWeb

TradingWeb 是为当前 TradingAgents 项目单独新增的 Web 界面，目录与原 CLI/核心包隔离在 `TradingWeb/` 下。

它提供：

- 多管理员账号登录（账号来自环境变量）
- 仿 CLI 的分析配置向导
- 自定义 LLM `base_url` / 网关地址
- 后台执行 TradingAgents 分析
- SQLite 持久化每次运行、每步日志、智能体状态、报告章节和最终决策
- 历史记录查看与删除
- Mock 模式，便于无 API Key 时验证页面与持久化链路

## 目录结构

```text
TradingWeb/
  app/                 # FastAPI 后端
  static/              # 无构建步骤的原生 JS SPA
  data/                # SQLite 数据库，已在 .gitignore 中忽略
  requirements.txt
  README.md
```

## 安装依赖

建议在项目根目录的同一个 Python 环境中安装：

```bash
pip install -r TradingWeb/requirements.txt
```

如果尚未安装主项目依赖，也需要先安装根项目：

```bash
pip install .
```

## 启动（真实模式）

PowerShell 示例：

```powershell
$env:TRADINGWEB_USERS="admin1:password1,admin2:password2"
$env:TRADINGWEB_SECRET="replace-with-a-long-random-secret"

# 可选：如果要使用自定义 OpenAI 兼容网关
$env:TRADINGAGENTS_LLM_BACKEND_URL="https://your-real-gateway.example.com/v1"
$env:OPENAI_API_KEY="your-gateway-or-provider-key"

cd TradingWeb
uvicorn app.main:app --host 0.0.0.0 --port 8731
```

浏览器打开：

```text
http://localhost:8731
```

登录账号来自：

```text
TRADINGWEB_USERS="用户名1:密码1,用户名2:密码2"
```

如果不设置，系统会回退到 `admin:admin`，仅用于本地临时测试。

## Mock 模式（推荐先验证）

Mock 模式不会调用任何 LLM，也不需要 API Key。它会模拟一次完整分析，生成执行日志、智能体状态、报告章节和最终 `HOLD` 决策。

```powershell
$env:TRADINGWEB_MOCK="1"
$env:TRADINGWEB_USERS="admin:test123"
$env:TRADINGWEB_SECRET="dev-secret"

cd TradingWeb
uvicorn app.main:app --host 127.0.0.1 --port 8731
```

然后访问：

```text
http://127.0.0.1:8731
```

使用 `admin / test123` 登录。

## 环境变量

### TradingWeb 自身

| 变量 | 说明 | 默认值 |
|---|---|---|
| `TRADINGWEB_USERS` | 多管理员账号，格式 `alice:secret1,bob:secret2` | `admin:admin` |
| `TRADINGWEB_SECRET` | HMAC Cookie 签名密钥 | 每次进程随机生成 |
| `TRADINGWEB_DB_PATH` | SQLite 路径 | `TradingWeb/data/tradingweb.db` |
| `TRADINGWEB_MOCK` | `1/true/yes/on` 开启模拟运行 | 关闭 |

### TradingAgents / LLM

Web 后端会读取项目根目录 `.env`，也可以直接通过容器/进程环境变量注入。

常用变量：

```bash
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_LLM_BACKEND_URL=https://your-real-gateway.example.com/v1
TRADINGAGENTS_DEEP_THINK_LLM=gpt-5.5
TRADINGAGENTS_QUICK_THINK_LLM=gpt-5.4-mini
OPENAI_API_KEY=...
```

注意：`TRADINGAGENTS_LLM_BACKEND_URL` 是当前选定 provider 的全局 base_url 覆盖项。Web 向导中也可以为单次运行填写“网关地址”，该值会写入本次运行配置。

不要把 `your-gateway.example.com` 这种占位域名放进 `.env`。如果容器日志出现 `httpx.ConnectError` / `Name or service not known` / `Connection refused`，优先检查：

1. `.env` 里的 `TRADINGAGENTS_LLM_BACKEND_URL` 是否是真实可访问地址；不用自定义网关时请注释掉或留空。
2. 网关是否必须带 `/v1`，例如 OpenAI 兼容网关通常是 `http://host.docker.internal:3000/v1`。
3. 如果网关跑在宿主机，本 compose 已内置 `host.docker.internal:host-gateway` 映射；容器内请不要使用 `localhost` 指宿主机。

## API 概览

- `POST /api/login`
- `POST /api/logout`
- `GET /api/me`
- `GET /api/options`
- `GET /api/options/models?provider=openai`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{id}`
- `GET /api/runs/{id}/steps?after_id=0`
- `DELETE /api/runs/{id}`

前端通过轮询 `/api/runs/{id}/steps` 实现无刷新更新。

## Docker / Compose 用法

当前没有修改根目录 `docker-compose.yml`。Web 使用独立的 `docker-compose.web.yml` 和 `TradingWeb/Dockerfile`，会把主项目与 TradingWeb 打包到同一个镜像里。

### GitHub 自动打包镜像

仓库包含 `.github/workflows/tradingweb-image.yml`，当推送到 `develop` / `main`、创建 `v*` tag，或手动触发 workflow 时，会自动构建并推送到 GitHub Container Registry：

```text
ghcr.io/osindex/tradingagents-tradingweb:develop
ghcr.io/osindex/tradingagents-tradingweb:main
ghcr.io/osindex/tradingagents-tradingweb:<git-tag>
ghcr.io/osindex/tradingagents-tradingweb:sha-<commit>
```

如果只想使用 GitHub 已打好的镜像，不在本机 build：

```bash
docker pull ghcr.io/osindex/tradingagents-tradingweb:develop
```

然后运行：

```bash
docker run --rm -p 8731:8731 \
  --env-file .env \
  -e TRADINGWEB_USERS="admin:change-me" \
  -e TRADINGWEB_SECRET="replace-with-random-secret" \
  -v tradingweb_data:/home/appuser/.tradingweb \
  -v tradingagents_data:/home/appuser/.tradingagents \
  ghcr.io/osindex/tradingagents-tradingweb:develop
```

如果 GHCR package 是私有的，先登录：

```bash
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

### 不改 CLI 源码的 profile 启动器

如果你想把 Web 里保存的 provider profile 直接拿去启动原始 `tradingagents` CLI，可以使用：

```bash
cd TradingWeb
python -m app.launcher --profile "OpenAI"
```

或者按 profile id：

```bash
cd TradingWeb
python -m app.launcher --profile-id 1
```

它会从 SQLite 里读取 profile，并在**子进程 env** 中注入：

- `TRADINGAGENTS_LLM_PROVIDER`
- `TRADINGAGENTS_LLM_BACKEND_URL`
- `TRADINGAGENTS_QUICK_THINK_LLM`
- `TRADINGAGENTS_DEEP_THINK_LLM`
- `TRADINGAGENTS_OUTPUT_LANGUAGE`

这样不会污染当前进程，也不会改 CLI 源码。

如果你想给 CLI 透传原始参数，可以在 launcher 后面继续加：

```bash
cd TradingWeb
python -m app.launcher --profile "OpenAI" -- --help
```

### 使用独立 compose（推荐）

准备 `.env`（可以由 `.env.local.example` 复制）。`docker-compose.web.yml` 不会修改原有 compose；`.env` 是可选的，但真实调用 LLM 时需要通过它或系统环境变量提供 API Key / base_url：

```bash
cp .env.local.example .env
```

启动：

```bash
TRADINGWEB_USERS="admin:change-me" \
TRADINGWEB_SECRET="replace-with-random-secret" \
docker compose -f docker-compose.web.yml up --build
```

如果想让 compose 直接拉 GitHub 自动构建的镜像，避免本地构建：

```bash
TRADINGWEB_IMAGE=ghcr.io/osindex/tradingagents-tradingweb:develop \
TRADINGWEB_USERS="admin:change-me" \
TRADINGWEB_SECRET="replace-with-random-secret" \
docker compose -f docker-compose.web.yml up --pull always --no-build
```

访问：

```text
http://localhost:8731
```

如果要先用 Mock 模式验证，不调用任何 LLM：

```bash
TRADINGWEB_MOCK=1 \
TRADINGWEB_USERS="admin:test123" \
TRADINGWEB_SECRET="dev-secret" \
docker compose -f docker-compose.web.yml up --build
```

SQLite 持久化在 compose volume `tradingweb_data` 中；TradingAgents 的记忆/缓存持久化在 `tradingagents_data` 中。

### Web 里的“接入商管理”

Web 新增了“接入商管理”页，可以直接管理 SQLite 里的 provider profiles：

- provider / base_url
- API key 环境变量名
- quick / deep 模型默认值
- thinking 参数
- 启用/禁用

新建分析时，优先从 profile 读取配置；如果 profile 里已经配置了模型和网关，向导里只需选择 profile 即可。

### 手动 docker build/run

如果不使用 compose，也可以直接构建 Web 镜像：

```bash
docker build -t tradingagents-web -f TradingWeb/Dockerfile .
docker run --rm -p 8731:8731 \
  --env-file .env \
  -e TRADINGWEB_USERS="admin:change-me" \
  -e TRADINGWEB_SECRET="replace-with-random-secret" \
  -e TRADINGWEB_DB_PATH="/home/appuser/.tradingweb/tradingweb.db" \
  -v tradingweb_data:/home/appuser/.tradingweb \
  -v tradingagents_data:/home/appuser/.tradingagents \
  tradingagents-web
```

如果自定义网关跑在宿主机上，容器内建议使用：

```text
http://host.docker.internal:<port>/v1
```

Linux Docker 如需访问宿主机，可在 compose 中加入：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

## 数据持久化

SQLite 表：

- `runs`：运行主记录、配置、状态、最终决策
- `run_steps`：每步消息、工具调用、状态变更、报告更新、错误
- `run_reports`：七个报告章节的最新内容

默认数据库文件：

```text
TradingWeb/data/tradingweb.db
```

该目录不会提交到 Git。
