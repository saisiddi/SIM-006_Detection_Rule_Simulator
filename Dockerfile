FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY sim_006 ./sim_006
COPY frontend ./frontend

# Run as an unprivileged user. 0.0.0.0 is the bind address *inside* the container only;
# what is published to the host is decided by docker-compose / the platform.
RUN useradd --system --no-create-home --uid 10001 app
USER app

ENV PORT=8000
EXPOSE 8000

# slim images have no curl; the stdlib is enough.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=2)"]

# $PORT lets a platform (e.g. Render) choose the port; defaults to 8000.
CMD ["sh", "-c", "exec python -m uvicorn sim_006.api:app --host 0.0.0.0 --port ${PORT}"]
