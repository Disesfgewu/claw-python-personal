"""Tests for Admin API endpoints (claw.core.gateway)."""
import pytest
import os


def test_admin_requires_token(client):
    """Admin endpoints must return 401 without valid token."""
    response = client.get("/admin/sessions")
    assert response.status_code == 401


def test_admin_list_sessions_with_token(client, monkeypatch):
    """GET /admin/sessions should return session list with valid token."""
    monkeypatch.setenv("CLAW_ADMIN_TOKEN", "test-admin-token")
    response = client.get(
        "/admin/sessions",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_admin_reload_skills_with_token(client, monkeypatch):
    """POST /admin/reload-skills should return reloaded count."""
    monkeypatch.setenv("CLAW_ADMIN_TOKEN", "test-admin-token")
    response = client.post(
        "/admin/reload-skills",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reloaded" in data
