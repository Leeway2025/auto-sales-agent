# Backend Dockerfile (FastAPI + Uvicorn)
# Build:   docker build -t voice-agent-backend:latest ./backend
# Run:     docker run --env-file ./.env -p 8000:8000 voice-agent-backend:latest

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# System deps (optional: for azure-cognitiveservices-speech runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

