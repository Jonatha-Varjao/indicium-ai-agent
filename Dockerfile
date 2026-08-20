FROM python:3.14-slim

RUN pip install --upgrade pip setuptools wheel -q

WORKDIR /app

COPY pyproject.toml README.md uv.lock ./
COPY src/ src/

RUN pip install uv -q && uv sync --frozen --no-dev -q 2>/dev/null || pip install . -q

COPY . .

RUN useradd -m app && chown -R app:app /app
USER app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import sys; sys.exit(0)"

ENTRYPOINT ["python", "scripts/run_report.py"]
