FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY requirements-cloud.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY sql ./sql

CMD ["sh", "-c", "uvicorn api:app --app-dir src --host 0.0.0.0 --port ${PORT}"]
