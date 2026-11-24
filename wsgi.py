"""WSGI entry point for production servers (for example, gunicorn wsgi:app)."""

from openlawoffice import create_app

app = create_app()
