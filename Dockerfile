FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Non-root user (uid 1000 = deploy на хосте, совпадает с владельцем volumes)
RUN useradd --uid 1000 --create-home appuser
COPY --chown=1000:1000 . .
RUN python manage.py collectstatic --noinput 2>/dev/null || true

USER appuser

EXPOSE 8000
