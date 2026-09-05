FROM python:3.11-slim

ARG GIT_COMMIT=dev
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 GIT_COMMIT=${GIT_COMMIT}
WORKDIR /app

COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} -r requirements.txt

COPY . /app/daemon

RUN mkdir -p /data
VOLUME ["/data"]

# non-root runtime
RUN useradd --create-home bot && chown -R bot:bot /app /data
USER bot

CMD ["python", "-m", "daemon.main"]
