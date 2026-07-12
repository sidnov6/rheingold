# Deploy — commands only (no secret values here)

RHEINGOLD ships as one Docker container (FastAPI on internal :8000 + Next.js
standalone on :7860, Next rewrites proxy `/api/*` to the API). The committed
DuckDB mart means the image needs no network at build time.

## Hugging Face Space (Docker SDK)

The repo README's YAML front-matter configures the Space (`sdk: docker`,
`app_port: 7860`). Push the repo to the Space, then set secrets in the UI.

```bash
# one-time: install the HF CLI and log in with a write token
pip install -U "huggingface_hub[cli]"
hf auth login                      # paste HF write token when prompted

# create the Space (Docker SDK) and push
hf repo create rheingold --repo-type space --space_sdk docker
git remote add hf https://huggingface.co/spaces/sidnov6/rheingold
git push hf main

# secrets / variables — set in the Space UI (Settings → Variables and secrets),
# or via CLI:
hf repo settings sidnov6/rheingold --repo-type space   # (UI is simpler for secrets)
```

Space **secrets** to add (Settings → Variables and secrets):
- `GROQ_API_KEY` — enables live IC-memo generation (fallback provider). Omit and
  memos show the graceful "engine unavailable" state; everything else works.
- (optional) `ANTHROPIC_API_KEY` — preferred memo provider if you have one.
- (optional) `RHEINGOLD_GROQ_MODEL` — defaults to `llama-3.3-70b-versatile`.

Space **variable** (not secret):
- `ALLOWED_ORIGIN=https://sidnov6-rheingold.hf.space`

Build arg (optional, for the health endpoint's build sha):
- `GIT_SHA` — set via Space build settings if desired; defaults to `dev`.

## GitHub

```bash
gh repo create sidnov6/rheingold --public --source . --remote origin \
  --description "Underwriting the Energiewende — cited IC memos for German onshore wind"
git push -u origin main
```

CI (`.github/workflows/ci.yml`) runs ruff + pytest + `next build` on push.

## Local container smoke test (optional, needs Docker)

```bash
docker build -t rheingold .
docker run --rm -p 7860:7860 -e ALLOWED_ORIGIN=http://localhost:7860 rheingold
# then open http://localhost:7860 and curl http://localhost:7860/api/health
```

## Secret hygiene

`.env` is gitignored and never committed. Keys live only in the Space's secret
store. Rotate any key that was ever pasted into a chat or logged.
