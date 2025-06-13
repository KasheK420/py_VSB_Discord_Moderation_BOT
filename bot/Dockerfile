# syntax=docker/dockerfile:1.7-labs

FROM python:3.11-slim

RUN pip install uv

COPY bot/ /app/vsb/bot/

COPY --parents pyproject.toml */pyproject.toml /app/vsb/

WORKDIR /app/vsb/

RUN set -eux; \
    uv sync --no-editable --no-cache --no-default-groups --group bot;

WORKDIR /app/vsb/bot

CMD ["bash", "run.sh"]