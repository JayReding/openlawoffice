"""Vendored branding assets and icon tests."""

from __future__ import annotations


def test_setup_page_uses_font_awesome_scale_icon(client):
    response = client.get("/setup")
    assert response.status_code == 200
    assert b"vendor/fontawesome/css/all.min.css" in response.data
    assert b"fa-solid fa-scale-balanced" in response.data
    assert b">OL<" not in response.data
    assert b"Icons: Font Awesome Free" in response.data


def test_font_awesome_css_is_served_locally(client):
    response = client.get("/static/vendor/fontawesome/css/all.min.css")
    assert response.status_code == 200
    assert b"fa-scale-balanced" in response.data
    assert b"../webfonts/fa-solid-900.woff2" in response.data


def test_font_awesome_solid_font_is_served(client):
    response = client.get("/static/vendor/fontawesome/webfonts/fa-solid-900.woff2")
    assert response.status_code == 200
    assert response.data.startswith(b"wOF2")


def test_favicon_is_served(client):
    response = client.get("/static/img/scale-balanced.svg")
    assert response.status_code == 200
    assert b"#132c3f" in response.data
    assert b"scale-balanced" in response.data


def test_authenticated_header_uses_scale_icon_fallback(app, client):
    from .conftest import create_admin

    create_admin(client)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"fa-solid fa-scale-balanced" in response.data


def test_login_page_uses_scale_icon_fallback(client):
    from .conftest import create_admin

    create_admin(client)
    client.post("/logout")
    response = client.get("/login")
    assert response.status_code == 200
    assert b"fa-solid fa-scale-balanced" in response.data
