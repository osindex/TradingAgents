# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Build graph (B-2 strategy):
#
#   cli-base ──> cli  (published as ghcr.io/osindex/tradingagents-cli:cli)
#                 ▲
#                 │  (web reuses the cli image as its base)
#                 │
#   web ── FROM ${CLI_IMAGE}
#
# The web image does NOT rebuild the TradingAgents core or re-run
# `pip install .`. Instead it starts FROM an existing cli image and only
# layers the TradingWeb dependencies + source on top. This makes web/tag
# builds fast because the slow `pip install .` lives entirely in the cli
# image, which is built once on the `cli` branch.
#
# CLI_IMAGE selects the base for the web stage:
#   * Local builds (docker compose --build): defaults to the in-tree `cli`
#     stage, so the build is fully self-contained with no extra args.
#   * CI web/tag builds: pass
#       --build-arg CLI_IMAGE=ghcr.io/osindex/tradingagents-cli:cli
#     to reuse the already-published cli image and skip the core install.
#
# Trade-off (accepted): the web image is version-locked to the cli image.
# Whenever core `tradingagents/` logic changes, the cli image must be
# republished first; the web build then picks it up on the next build.
# ---------------------------------------------------------------------------

# Declared globally (before the first FROM) so BuildKit treats it as a build
# arg even when building `--target web` directly. Defaults to the in-tree
# `cli` stage for self-contained local builds.
ARG CLI_IMAGE=cli

FROM python:3.12-slim AS cli-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install the TradingAgents core package and its runtime dependencies once.
COPY pyproject.toml uv.lock ./
COPY tradingagents ./tradingagents
COPY cli ./cli
RUN python -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --no-cache-dir -U pip setuptools wheel \
 && pip install --no-cache-dir .

FROM cli-base AS cli

RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingweb

USER appuser
WORKDIR /home/appuser/app

COPY --from=cli-base --chown=appuser:appuser /build/tradingagents ./tradingagents
COPY --from=cli-base --chown=appuser:appuser /build/cli ./cli

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["tradingagents"]

# ---------------------------------------------------------------------------
# Web image: starts FROM an existing cli image (local `cli` stage by default,
# or a published ghcr cli image in CI). It inherits the venv at /opt/venv and
# the core tradingagents/ code under /home/appuser/app, then only adds the
# TradingWeb dependencies and source.
# ---------------------------------------------------------------------------
FROM ${CLI_IMAGE} AS web

# Root is needed to install extra deps and write the TradingWeb source; the
# cli image runs as appuser, so switch up then back down.
USER root
WORKDIR /home/appuser/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TRADINGWEB_DB_PATH=/home/appuser/.tradingweb/tradingweb.db

# TradingWeb-only dependencies on top of the inherited core venv.
COPY TradingWeb/requirements.txt /tmp/tradingweb-requirements.txt
RUN . /opt/venv/bin/activate \
 && pip install --no-cache-dir -r /tmp/tradingweb-requirements.txt

# TradingWeb source.
COPY --chown=appuser:appuser TradingWeb ./TradingWeb

USER appuser
WORKDIR /home/appuser/app/TradingWeb

EXPOSE 8731

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8731"]
