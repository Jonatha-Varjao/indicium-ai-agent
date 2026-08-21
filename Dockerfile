FROM python:3.14-slim

RUN pip install --upgrade pip setuptools wheel -q

WORKDIR /app

COPY pyproject.toml README.md uv.lock ./
COPY src/ src/

RUN pip install uv -q && uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

COPY . .

RUN useradd -m app && chown -R app:app /app
USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "from indicium_ai_agent.graph import build_graph"

ENTRYPOINT ["python", "scripts/run_report.py"]
