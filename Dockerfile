FROM python:3.12-slim AS builder

ARG TZ=Asia/Shanghai

WORKDIR /app

ENV PATH=/root/.local/bin:$PATH
RUN pip install pipx && \
    pipx ensurepath && \
    pipx install poetry
RUN apt update && \
    apt install -y --no-install-recommends git build-essential cmake && \
    rm -rf /var/lib/apt/lists/*

COPY . .

RUN poetry config virtualenvs.in-project true && \
    poetry lock && \
    poetry install --no-interaction --no-ansi && \
    /app/.venv/bin/python -m compileall -q /app/javsp

FROM python:3.12-slim AS runner

ARG TZ=Asia/Shanghai
ENV TZ=${TZ}

WORKDIR /app

COPY --from=builder /app/ /app/

ENTRYPOINT ["/app/.venv/bin/server"]
