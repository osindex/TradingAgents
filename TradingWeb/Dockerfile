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

FROM cli-base AS web-build

COPY TradingWeb/requirements.txt /tmp/tradingweb-requirements.txt
RUN . /opt/venv/bin/activate \
 && pip install --no-cache-dir -r /tmp/tradingweb-requirements.txt
# Keep TradingWeb source in /build so later stages can COPY it by stable path.
COPY TradingWeb /build/TradingWeb

FROM python:3.12-slim AS web

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADINGWEB_DB_PATH=/home/appuser/.tradingweb/tradingweb.db

COPY --from=web-build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingweb

USER appuser
WORKDIR /home/appuser/app

# Bring in the runtime code after dependencies are cached.
COPY --from=cli-base --chown=appuser:appuser /build/tradingagents ./tradingagents
COPY --from=cli-base --chown=appuser:appuser /build/cli ./cli
COPY --from=web-build --chown=appuser:appuser /build/TradingWeb ./TradingWeb

WORKDIR /home/appuser/app/TradingWeb

EXPOSE 8731

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8731"]
