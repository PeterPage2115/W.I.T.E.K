"""WSGI entry point for gunicorn (web-only, no bot/scheduler)."""
from app import create_app

app = create_app()
