FROM ghcr.io/astral-sh/uv:0.13.10 AS uv
FROM python:3.13.18-slim-trixie
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev && \
    groupadd --gid 10001 simulator && \
    useradd --uid 10001 --gid 10001 --no-create-home simulator
USER 10001:10001
CMD ["python", "-m", "flood_simulator"]
