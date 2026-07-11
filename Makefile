.PHONY: data engine-test agents-test api-test test dev dev-api dev-web backtest showcase deploy lint

# ---- data pipelines (order matters: units before fleet before resource) ----
data:
	uv run python data/pipelines/download_mastr.py
	uv run python data/pipelines/download_smard.py
	uv run python data/pipelines/marktwerte.py
	uv run python data/pipelines/gwa_download.py
	uv run python data/pipelines/build_fleet.py
	uv run python data/pipelines/resource.py
	uv run python data/pipelines/build_mart.py

# ---- tests ----
engine-test:
	uv run pytest packages/engine/tests -q

agents-test:
	uv run pytest packages/agents/tests -q

api-test:
	uv run pytest apps/api/tests -q

test: engine-test agents-test api-test

lint:
	uv run ruff check packages apps/api data/pipelines
	uv run ruff format --check packages apps/api data/pipelines

# ---- dev ----
dev-api:
	uv run uvicorn main:app --app-dir apps/api --reload --port 8000

dev-web:
	cd apps/web && npm run dev

dev:
	$(MAKE) -j2 dev-api dev-web

# ---- artifacts ----
backtest:
	uv run python -m rheingold_engine.backtest --out data/mart/backtest.json

showcase:
	uv run python data/pipelines/build_showcase.py

deploy:
	@echo "web: vercel --prod (apps/web) | api: see render.yaml / fly.toml" && exit 1
