from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


def run_browser_preview(arguments: dict[str, Any]) -> dict[str, Any]:
    artifact_id = str(arguments.get("artifact_id") or "")
    url = str(arguments.get("url") or (f"/api/v1/artifacts/{artifact_id}/preview" if artifact_id else "/api/v1/health"))
    started = time.perf_counter()
    access = _check_access(url)
    playwright = _try_playwright(url) if _is_absolute_url(url) else _playwright_fallback("relative URL checked through ASGI")
    capability_level = "real" if access["accessible"] and playwright.get("available") else "fallback"
    return {
        "status": "succeeded" if access["accessible"] else "failed",
        "capability_level": capability_level,
        "preview_url": url,
        "accessible": access["accessible"],
        "status_code": access["status_code"],
        "response_summary": access["summary"],
        "playwright": playwright,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def _check_access(url: str) -> dict[str, Any]:
    if _is_absolute_url(url):
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                response = client.get(url)
            return {
                "accessible": response.status_code < 500,
                "status_code": response.status_code,
                "summary": response.text[:1_000],
            }
        except Exception as exc:
            return {"accessible": False, "status_code": None, "summary": str(exc)}
    from fastapi.testclient import TestClient

    from app.main import app

    path = url if url.startswith("/") else f"/{url}"
    response = TestClient(app, raise_server_exceptions=False).get(path)
    return {
        "accessible": response.status_code < 500,
        "status_code": response.status_code,
        "summary": response.text[:1_000],
    }


def _try_playwright(url: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _playwright_fallback(f"playwright unavailable: {exc}")
    target = url if _is_absolute_url(url) else get_settings().artifact_base_url.rstrip("/") + "/" + url.lstrip("/")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            response = page.goto(target, wait_until="domcontentloaded", timeout=10_000)
            title = page.title()
            browser.close()
        return {
            "available": True,
            "title": title,
            "status_code": response.status if response else None,
            "checked_url": target,
        }
    except Exception as exc:
        return _playwright_fallback(f"playwright check failed: {exc}")


def _playwright_fallback(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def _is_absolute_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
