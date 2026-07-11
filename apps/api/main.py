"""Uvicorn entry point: uvicorn main:app --app-dir apps/api"""

from rheingold_api.app import create_app

app = create_app()
