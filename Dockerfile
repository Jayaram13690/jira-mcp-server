FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY run_server.py ./

# Write logs immediately instead of buffering them
ENV PYTHONUNBUFFERED=1

EXPOSE 9002

# Run uvicorn directly rather than through run_server.py.
# run_server.py calls uvicorn with --reload via os.system(), which is a
# development pattern: it needs a file watcher, spawns uvicorn as a child
# process, and does not pass signals through properly. In a container that
# can leave the container "running" while nothing is actually serving
# requests - which shows up as connection timeouts rather than a crash.
CMD ["uv", "run", "uvicorn", "src.servers.server:mcp_app", \
     "--host", "0.0.0.0", "--port", "9002"]