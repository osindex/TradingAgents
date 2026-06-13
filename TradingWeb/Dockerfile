FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir . \
 && pip install --no-cache-dir -r TradingWeb/requirements.txt

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADINGWEB_DB_PATH=/home/appuser/.tradingweb/tradingweb.db

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingweb

USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build .

WORKDIR /home/appuser/app/TradingWeb

EXPOSE 8731

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8731"]
