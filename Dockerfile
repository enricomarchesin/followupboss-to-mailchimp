FROM python:3.9.11-slim-bullseye
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update -y \
    && apt-get install -y \
      locales \
      curl \
    && rm -rf /var/lib/apt/lists/*
ENV LANG en_US.UTF-8
RUN update-locale && locale-gen $LANG

ARG PIP_VERSION=22.3.1
ARG POETRY_VERSION=1.3.2
RUN pip install --no-cache-dir pip==${PIP_VERSION} poetry==${POETRY_VERSION}

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN poetry config virtualenvs.create false
RUN poetry config --list
RUN poetry env info --no-interaction
RUN poetry show --tree --no-interaction

RUN poetry install --no-root --no-interaction

COPY . /app

ENTRYPOINT [ "poetry", "run" ]
CMD ["./sync.py"]
