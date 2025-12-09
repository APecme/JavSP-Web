FROM python:3.12-slim AS builder

WORKDIR /app

ENV PATH=/root/.local/bin:$PATH
RUN pip install pipx && \
    pipx ensurepath && \
    pipx install poetry
RUN apt update && apt install -y git

COPY . .

RUN poetry config virtualenvs.in-project true && \
    poetry lock && \
    poetry install --no-interaction --no-ansi

FROM python:3.12-slim AS runner

WORKDIR /app

COPY --from=builder /app/ /app/

ENTRYPOINT ["/app/.venv/bin/server"]
