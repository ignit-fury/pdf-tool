# Production image deliberately excludes test renderers, dev tools and the corpus.
FROM node:22-bookworm-slim AS client
WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
COPY engine/data/search-unicode-15.1.json /engine/data/search-unicode-15.1.json
RUN npm run build

FROM python:3.13-slim-trixie@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY engine ./engine
COPY server ./server
COPY fonts ./fonts
COPY --from=client /client/dist ./client/dist
ENV PDF_TOOL_ENV=production PDF_TOOL_SCRATCH_ROOT=/dev/shm PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8000
CMD [".venv/bin/python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
