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
2. 网关是否必须带 `/v1`。例如 OpenAI 兼容网关通常是 `http://host.docker.internal:3000/v1`。
3. **Linux 注意**：`host.docker.internal` 在 Linux 上通常**不会自动可用**。本仓库的 `docker-compose.web.yml` / `docker-compose.web.image.yml` 已显式加了 `extra_hosts: host.docker.internal:host-gateway`，但如果你自己复制 compose、或者用的是老版本 Docker/Compose，仍然可能解析失败。
4. 如果 `host.docker.internal` 不通，请改用：
   - 宿主机局域网 IP，例如 `http://192.168.1.10:3000/v1`
   - 或在 compose 里继续保留 `extra_hosts: - "host.docker.internal:host-gateway"`
   - 容器内请不要使用 `localhost` 指宿主机，因为那只会指向容器自己。

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

当前没有修改根目录 `docker-compose.yml`。Web 使用独立的 `docker-compose.web.yml` 和 `TradingWeb/Dockerfile`。
在 `tradingweb-image.yml` CI 中，CLI 与 Web 已经分 target 打包并分别发布成两份镜像：`tradingagents-cli` 和 `tradingagents-tradingweb`。

### 三种 compose 的区别

- `docker-compose.web.yml`：通用版。既支持本地构建，也支持通过 `TRADINGWEB_IMAGE` 拉取镜像运行；保留 `.env`、`host.docker.internal` 和本地调试兼容项。
- `docker-compose.web.image.yml`：镜像运行版。默认就是从 GHCR 拉镜像，适合“我已经有打包好的镜像，只想运行”。
- `docker-compose.web.min.yml`：最小版。只保留镜像、端口和数据卷，适合生产部署或极简运行。

最小版和现在版本的区别是：最小版删掉了 `.env` 兼容、宿主机网关映射、额外环境变量覆盖等方便开发/排错的配置，所以更简洁，但也更依赖你已经把运行环境准备好。

### GitHub 自动打包镜像

仓库包含 `.github/workflows/tradingweb-image.yml`，构建策略为：

- `tradingagents-cli`：仅在 `cli` 分支推送时构建
- `tradingagents-tradingweb`：在 `main` 推送与 `v*` tag 时构建

仓库 push 时满足路径变更即可触发上述规则的相关任务（手动触发也可按规则指定）：

```text
ghcr.io/osindex/tradingagents-cli:cli
ghcr.io/osindex/tradingagents-cli:<branch-tag>
ghcr.io/osindex/tradingagents-cli:sha-<commit>

ghcr.io/osindex/tradingagents-tradingweb:main
ghcr.io/osindex/tradingagents-tradingweb:<git-tag>
ghcr.io/osindex/tradingagents-tradingweb:sha-<commit>
```

如果只想使用 GitHub 已打好的镜像，不在本机 build：

```bash
docker pull ghcr.io/osindex/tradingagents-cli:cli
docker pull ghcr.io/osindex/tradingagents-tradingweb:main
```

如果你的机器是 ARM64（例如 Apple Silicon）而镜像还没来得及发布多架构版本，可能会看到：

```text
no matching manifest for linux/arm64/v8
```

临时绕过方式：

```bash
docker pull --platform linux/amd64 ghcr.io/osindex/tradingagents-tradingweb:main
```

但更推荐等 workflow 发布了 `linux/amd64` + `linux/arm64` 双架构镜像后再直接拉取，这样就不需要手工指定平台了。

### 分阶段构建说明

TradingWeb 镜像现在采用分阶段构建：

- **CLI 基础层**：安装 TradingAgents 核心代码和依赖
- **Web 扩展层**：只安装 TradingWeb 的额外依赖并拷贝 Web 源码

这样在大多数情况下，改 TradingWeb 前端/后端只会重建上层，不会把原 CLI 依赖整层重装。只有当 `tradingagents/`、`cli/`、`pyproject.toml` 或 `uv.lock` 变化时，基础层才会重建。

双镜像由同一份 workflow 管理，但按分支与标签规则分离构建：

- `cli` 目标：仅在 `cli` 分支
- `tradingweb` 目标：仅在 `main` 与 `v*` tag

### 双容器运行（mix-compose）

如果你想把 CLI 和 Web 完全拆成两个容器运行，请使用根目录的 `docker-compose.mix.yml`。

- `tradingcli`：负责执行 TradingAgents CLI / 运行引擎
- `tradingweb`：负责登录、provider 管理、队列、历史、导出

两个容器通过共享卷协作：

- `tradingweb_data`：SQLite、memory、checkpoint、results 等共享数据
- `tradingagents_data`：TradingAgents 自己的数据缓存

这套方案不要求两个容器互相 import 源码；它们只通过 DB/文件路径/环境变量契约通信。

然后运行：

```bash
# CLI 服务
docker pull ghcr.io/osindex/tradingagents-cli:cli

# Web 服务
docker pull ghcr.io/osindex/tradingagents-tradingweb:main

docker compose -f docker-compose.mix.yml up --pull always
```

如果 GHCR package 是私有的，先登录：

```bash
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

### 不改 CLI 源码的 profile 启动器

如果你想把 Web 里保存的 provider profile 直接拿去启动原始 `tradingagents` CLI，可以使用：

```bash
cd TradingWeb
python -m app.launcher --profile "OpenAI" --username admin
```

或者按 profile id：

```bash
cd TradingWeb
python -m app.launcher --profile-id 1 --username admin
```

它会从 SQLite 里读取 profile，并在**子进程 env** 中注入：

- `TRADINGAGENTS_LLM_PROVIDER`
- `TRADINGAGENTS_LLM_BACKEND_URL`
- `TRADINGAGENTS_QUICK_THINK_LLM`
- `TRADINGAGENTS_DEEP_THINK_LLM`
- `TRADINGAGENTS_OUTPUT_LANGUAGE`
- `TRADINGAGENTS_MEMORY_LOG_PATH`

这样不会污染当前进程，也不会改 CLI 源码。

如果你想给 CLI 透传原始参数，可以在 launcher 后面继续加：

```bash
cd TradingWeb
python -m app.launcher --profile "OpenAI" -- --help
```

### 按用户隔离决策记忆

原框架的决策记忆默认是共享的 markdown 文件。TradingWeb 不改原框架源码，而是在 Web/launcher 这一层按登录用户注入独立的 `TRADINGAGENTS_MEMORY_LOG_PATH`，例如：

```text
TradingWeb/data/memory/admin/trading_memory.md
TradingWeb/data/memory/alice/trading_memory.md
```

这样每个用户看到的是自己的历史记忆，不会互相污染；CLI 继续保持原有逻辑，只是运行时拿到不同的进程环境变量。

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
TRADINGWEB_IMAGE=ghcr.io/osindex/tradingagents-tradingweb:main \
TRADINGWEB_USERS="admin:change-me" \
TRADINGWEB_SECRET="replace-with-random-secret" \
docker compose -f docker-compose.web.yml up --pull always --no-build
```

如果你只想运行“打包后的镜像”，可以直接用专门的镜像 compose：

```bash
TRADINGWEB_IMAGE=ghcr.io/osindex/tradingagents-tradingweb:main \
TRADINGWEB_USERS="admin:change-me" \
TRADINGWEB_SECRET="replace-with-random-secret" \
docker compose -f docker-compose.web.image.yml up --pull always
```

如果你想要更适合生产部署的最小版：

```bash
TRADINGWEB_IMAGE=ghcr.io/osindex/tradingagents-tradingweb:main \
TRADINGWEB_USERS="admin:change-me,alice:strong-password" \
TRADINGWEB_SECRET="replace-with-random-secret" \
docker compose -f docker-compose.web.min.yml up --pull always
```

最小版如何添加默认用户：通过 `TRADINGWEB_USERS` 环境变量传入，格式是 `用户名:密码,用户名2:密码2`。例如：

```bash
TRADINGWEB_USERS="admin:change-me,alice:strong-password"
```

如果不设置，最小版会默认使用 `admin:admin`，仅建议本地临时测试。生产环境请务必改成自己的强密码，并同步设置 `TRADINGWEB_SECRET`。

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

> 权限说明：接入商配置仅 **admin** 可见/可改；普通用户只会看到自己的历史记录和运行详情。

### CLI → Web 能力优先级（建议实现顺序）

1. **历史查询与查看详情**：Web 已有 run 列表、run detail、steps 日志。
2. **checkpoint 恢复 / 清理**：把 CLI 的 `--checkpoint` / `--clear-checkpoints` 做成按钮和开关。
3. **用户隔离记忆**：当前已通过 `TRADINGAGENTS_MEMORY_LOG_PATH` 按用户隔离。
4. **运行重放 / 复制配置**：一键用历史 run 的配置重新发起分析。
5. **结果导出**：导出 Markdown、JSON、日志包。
6. **批量运行 / 队列 / 定时任务**：更高阶的 CLI 扩展。

其中，**admin 可以查看全部策略/所有用户的运行记录**；普通用户只能看到自己的 run。provider 配置页与 checkpoint 管理也仅对 admin 开放；普通用户只能使用 admin 已配置好的 profile。

### 已在 Web 中补齐的 CLI 能力按钮

- **复制并重跑**：在 run 详情页和历史列表都可一键复用当前配置重新发起分析。
- **导出结果**：支持导出 JSON；run 详情页还可导出 Markdown。
- **checkpoint 管理**：仅 admin 可查询和清理 checkpoint。
- **记忆管理**：可查看并清理当前用户的 memory log。
- **中止运行**：运行中可在详情页直接取消。
- **批量运行**：历史页已接到 `POST /api/runs/batch`。
- **批量队列页**：可在“批量队列”中提交多个 ticker、查看状态、跳转详情、取消运行。

### LLM 厂商 / provider 的权限规则

- **admin**：可以进入“接入商管理”页，新增 / 编辑 / 删除 provider profile，配置网关地址和 API key 环境变量名。
- **普通用户**：只能在“新建分析”里选择 admin 已配置好的 provider profile；**不能手填网关地址**，也不能进入“接入商管理”页。
- 这样能确保 provider 配置仍由 admin 统一管理，但普通用户仍可在分析时选择已有的供应商配置。

### 还可以继续扩展的 CLI 能力

- 定时运行
- 更细的 checkpoint 恢复点展示
- 记忆检索和标签化

### 当前的批量运行说明

Web 已经有独立的“批量队列”页：可以提交多个 ticker、查看每个 run 的状态、跳转详情、取消运行。队列调度仍是最小可用版本（直接创建多个 run 并轮询），但界面上已经是独立队列页了。

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
