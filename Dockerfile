FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY project.py backend.py app.py ./

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app

USER appuser

EXPOSE 5000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT app:app"]