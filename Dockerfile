FROM python:3.14-slim

RUN pip install --upgrade pip setuptools wheel -q

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install . -q

COPY . .

ENTRYPOINT ["python", "scripts/run_report.py"]
