FROM python:3.12-slim

ARG JAVSP_WEB_RELEASE_LABEL=""
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 JAVSP_WEB_HOST=0.0.0.0 JAVSP_WEB_PORT=8090 JAVSP_WEB_DOCKER=1 JAVSP_WEB_TIMEZONE=Asia/Shanghai TZ=Asia/Shanghai JAVSP_WEB_RELEASE_LABEL=${JAVSP_WEB_RELEASE_LABEL}

COPY requirements.txt ./
COPY vendor/JavSP ./vendor/JavSP
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver novnc x11vnc xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY javsp_web ./javsp_web
COPY launcher.py README.md docker-entrypoint.sh ./
RUN chmod 755 /app/docker-entrypoint.sh
RUN mkdir -p /app/data

EXPOSE 8090
VOLUME ["/app/data", "/video"]
CMD ["/app/docker-entrypoint.sh"]
