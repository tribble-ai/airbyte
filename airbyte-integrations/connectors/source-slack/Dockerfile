FROM python:3.9.11-alpine3.15 as base

FROM base as builder
WORKDIR /airbyte/integration_code

RUN apk --no-cache upgrade \
    && pip install --upgrade pip \
    && apk --no-cache add tzdata build-base

COPY pyproject.toml poetry.lock README.md ./
COPY source_slack ./source_slack
RUN pip install --prefix=/install .

FROM base
WORKDIR /airbyte/integration_code

COPY --from=builder /install /usr/local
COPY --from=builder /usr/share/zoneinfo/Etc/UTC /etc/localtime
RUN echo "Etc/UTC" > /etc/timezone

RUN apk --no-cache add bash

COPY main.py ./
COPY source_slack ./source_slack

ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

LABEL io.airbyte.version=0.3.9
LABEL io.airbyte.name=airbyte/source-slack
