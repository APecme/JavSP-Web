FROM python:3.12-slim

ARG JAVSP_WEB_RELEASE_LABEL=""
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 JAVSP_WEB_HOST=0.0.0.0 JAVSP_WEB_PORT=8090 JAVSP_WEB_DOCKER=1 JAVSP_WEB_TIMEZONE=Asia/Shanghai TZ=Asia/Shanghai JAVSP_WEB_RELEASE_LABEL=${JAVSP_WEB_RELEASE_LABEL}

COPY requirements.txt ./
COPY vendor/JavSP ./vendor/JavSP
RUN pip install --no-cache-dir -r requirements.txt

COPY javsp_web ./javsp_web
COPY launcher.py README.md ./
RUN mkdir -p /app/data

EXPOSE 8090
VOLUME ["/app/data", "/video"]
CMD ["python", "-m", "javsp_web.server"]
