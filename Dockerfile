# RHEINGOLD — Hugging Face Docker Space (single container, port 7860).
# Two processes: FastAPI (uvicorn, 127.0.0.1:8000, internal) + Next.js
# standalone server (0.0.0.0:7860, public). Next rewrites proxy /api/* to
# the internal FastAPI, so the browser only ever talks to :7860.

# ---------------------------------------------------------------- web build
FROM node:20-slim AS web-build

WORKDIR /build/web

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/ ./

# NEXT_PUBLIC_API_URL="" → client code fetches relative "/api/..." URLs.
# API_INTERNAL_URL is baked into the rewrites manifest at build time.
# NEXT_OUTPUT_STANDALONE=1 → output:'standalone' (see next.config.mjs) so the
# runtime stage needs no node_modules.
# next/font (IBM Plex, Newsreader) fetches Google Fonts CSS at build time —
# fine on HF builders (network available). If builds ever flake on font
# fetches, pre-record responses via NEXT_FONT_GOOGLE_MOCKED_RESPONSES.
ENV NEXT_PUBLIC_API_URL="" \
    API_INTERNAL_URL=http://127.0.0.1:8000 \
    NEXT_OUTPUT_STANDALONE=1 \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ------------------------------------------------------------------ runtime
FROM node:20-slim AS runtime

# bookworm ships Python 3.11 — matches requires-python >=3.11 / ruff py311.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3.11 python3.11-venv curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# HF Spaces requirement: non-root user with uid 1000 named 'user',
# writable HOME.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    UV_PYTHON=python3.11 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
RUN chown user:user /app
USER user

# Python side: workspace layout must be preserved (repo_root() in
# apps/api/rheingold_api/deps.py resolves data/ and docs/ relative to it).
COPY --chown=user:user pyproject.toml uv.lock ./
COPY --chown=user:user packages/ packages/
COPY --chown=user:user apps/api/ apps/api/
# --no-dev + --no-group pipelines: dev tools and the heavy pipeline stack
# (pandas/rasterio/open-mastr) are build-time only; the API serves from the
# prebuilt DuckDB mart.
RUN uv sync --frozen --no-dev --no-group pipelines --all-packages

# Prebuilt data mart + manual ground-truth CSVs + docs (read at runtime by
# /api/market and the methodology content).
COPY --chown=user:user data/mart/ data/mart/
COPY --chown=user:user data/manual/ data/manual/
COPY --chown=user:user docs/ docs/

# Next standalone server + static assets + public files.
COPY --chown=user:user --from=web-build /build/web/.next/standalone apps/web/
COPY --chown=user:user --from=web-build /build/web/.next/static apps/web/.next/static
COPY --chown=user:user --from=web-build /build/web/public apps/web/public

COPY --chown=user:user start.sh ./
# COPY preserves the executable bit set in the repo; keep it explicit anyway.
USER root
RUN chmod +x /app/start.sh
USER user

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA} \
    RHEINGOLD_MART=/app/data/mart/rheingold.duckdb \
    PORT=7860

EXPOSE 7860

CMD ["/app/start.sh"]
