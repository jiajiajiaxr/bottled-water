from typing import Any

from pathlib import Path

from db.models import Deployment

from app.api.deployments import _is_backend_proxy_path, _normalize_backend_proxy_path
from app.api.deployments import _backend_proxy_candidate_paths
from app.services.backend_process_manager import BackendProcessManager
from app.services.deployments import (
    _deployment_inline_script_syntax_check,
    _deployment_fullstack_check,
    _deployment_proxy_base_for_url,
    _inject_api_base_global,
    _normalize_cdn_scripts,
)


def test_deployment_normalizes_module_jsx_script_for_browser_runtime() -> None:
    html = """<!doctype html>
<html>
<head></head>
<body>
  <div id="root"></div>
  <script type="module">
    const { Table } = antd;
    function App() {
      return <Table dataSource={[]} />;
    }
    const root = ReactDOM.createRoot(document.getElementById("root"));
    root.render(<App />);
  </script>
</body>
</html>"""

    normalized = _normalize_cdn_scripts(html)

    assert "@babel/standalone" in normalized
    assert '<script type="module">' not in normalized
    assert '<script type="text/babel">' in normalized
    assert "root.render(<App />);" in normalized


def test_deployment_places_dayjs_before_antd_runtime() -> None:
    html = """<!doctype html>
<html>
<head>
  <script src="https://cdn.jsdelivr.net/npm/antd@5.12.5/dist/antd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dayjs@1.11.10/dayjs.min.js"></script>
</head>
<body><div id="root"></div></body>
</html>"""

    normalized = _normalize_cdn_scripts(html)

    assert normalized.count("dayjs.min.js") == 1
    assert normalized.index("dayjs.min.js") < normalized.index("antd.min.js")


def test_deployment_proxy_base_matches_generated_api_style() -> None:
    assert (
        _deployment_proxy_base_for_url(
            "http://localhost:8000/api",
            "/api/v1/deployments/dep/site",
            "/api/v1/deployments/dep/site/api",
        )
        == "/api/v1/deployments/dep/site/api"
    )
    assert (
        _deployment_proxy_base_for_url(
            "http://localhost:8000",
            "/api/v1/deployments/dep/site",
            "/api/v1/deployments/dep/site/api",
        )
        == "/api/v1/deployments/dep/site"
    )


def test_backend_proxy_normalizes_duplicate_api_prefix() -> None:
    assert _normalize_backend_proxy_path("api/api/persons") == "api/persons"
    assert _normalize_backend_proxy_path("/api/api/persons/1") == "api/persons/1"
    assert _normalize_backend_proxy_path("api/persons") == "api/persons"


def test_backend_proxy_recognizes_exact_api_health_path() -> None:
    assert _is_backend_proxy_path("api") is True
    assert _is_backend_proxy_path("api/") is True
    assert _is_backend_proxy_path("api/api/products") is True
    assert _is_backend_proxy_path("items") is True
    assert _is_backend_proxy_path("items/1") is True
    assert _is_backend_proxy_path("health") is True
    assert _is_backend_proxy_path("docs") is True
    assert _is_backend_proxy_path("openapi.json") is True
    assert _is_backend_proxy_path("index.html") is False
    assert _is_backend_proxy_path("assets/app.js") is False


def test_backend_proxy_falls_back_for_common_health_paths() -> None:
    assert _backend_proxy_candidate_paths("api/health") == ["api/health", "health"]
    assert _backend_proxy_candidate_paths("api/openapi.json") == [
        "api/openapi.json",
        "openapi.json",
    ]
    assert _backend_proxy_candidate_paths("api/items") == ["api/items", "items"]
    assert _backend_proxy_candidate_paths("items") == ["items", "api/items"]


def test_generated_backend_ready_path_requires_successful_http_response(monkeypatch) -> None:
    import urllib.error
    import urllib.request

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

    def fake_urlopen(url: str, timeout: int):
        if url.endswith("/openapi.json"):
            raise urllib.error.HTTPError(url, 404, "not found", None, None)
        if url.endswith("/health"):
            return DummyResponse()
        raise AssertionError(f"unexpected probe url: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert BackendProcessManager._ready_path(9001) == "/health"


def test_deployment_injects_global_api_base_once() -> None:
    html = "<!doctype html><html><head></head><body></body></html>"
    injected = _inject_api_base_global(html, "/api/v1/deployments/dep/site/api")
    assert "window.AGENTHUB_API_BASE_URL" in injected
    assert injected.count("window.AGENTHUB_API_BASE_URL") == 1
    assert _inject_api_base_global(injected, "/other").count("window.AGENTHUB_API_BASE_URL") == 1


def test_deployment_rewrites_dynamic_localhost_api_base(tmp_path: Path) -> None:
    from app.services.deployments import _inject_backend_url_to_site

    deployment = Deployment(
        id="dep-dynamic",
        artifact_id="artifact-test",
        mode="preview_link",
        config={},
    )
    site_root = tmp_path / "deployments" / deployment.id / "site"
    site_root.mkdir(parents=True)
    index = site_root / "index.html"
    index.write_text(
        """<!doctype html><html><head></head><body>
<script>
const API_BASE_URL = window.location.protocol + '//' + window.location.hostname + ':8000';
</script>
</body></html>""",
        encoding="utf-8",
    )

    import app.services.deployments as deployments

    original_root = deployments.deployment_site_root
    deployments.deployment_site_root = lambda _deployment_id: site_root
    try:
        _inject_backend_url_to_site(deployment, 9013)
    finally:
        deployments.deployment_site_root = original_root

    content = index.read_text(encoding="utf-8")
    assert (
        "const API_BASE_URL = '/api/v1/deployments/dep-dynamic/site';"
        in content
    )


def test_fullstack_health_fails_when_backend_entry_did_not_start(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text(
        "<!doctype html><div id='root'></div><script>fetch('/api/items')</script>",
        encoding="utf-8",
    )
    deployment = Deployment(
        id="dep-test",
        artifact_id="artifact-test",
        mode="preview_link",
        config={
            "backend_start_failed": True,
            "backend_start_error": "backend failed to start",
        },
    )

    check = _deployment_fullstack_check(index, deployment, "preview_link", True)

    assert check["status"] == "failed"
    assert "backend failed to start" in check["message"]


def test_fullstack_health_fails_when_backend_started_but_frontend_is_mock_only(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text(
        """<!doctype html>
<html>
<body>
<div id="root"></div>
<script>
  const mockData = [{ id: 1, name: "demo" }];
  ReactDOM.createRoot(document.getElementById("root")).render("mock");
</script>
</body>
</html>""",
        encoding="utf-8",
    )
    deployment = Deployment(
        id="dep-test",
        artifact_id="artifact-test",
        mode="preview_link",
        config={"backend_port": 9001},
    )

    check = _deployment_fullstack_check(index, deployment, "preview_link", True)

    assert check["status"] == "failed"
    assert "mock-only" in check["message"]


def test_deployment_health_fails_on_inline_script_syntax_error(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text(
        """<!doctype html>
<html>
<body>
<div id="root"></div>
<script>
  React.createElement("div", { title: "broken" };
</script>
</body>
</html>""",
        encoding="utf-8",
    )

    check = _deployment_inline_script_syntax_check(index, "preview_link", True)

    assert check["status"] == "failed"
    assert "SyntaxError" in check["message"]


def test_deployment_request_contract(
    client: Any,
    api_paths: dict[str, str],
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        api_paths["deployments"],
        json={"artifact_id": "acceptance-artifact", "environment": "preview"},
        headers=auth_headers,
    )

    assert response.status_code in {200, 201, 202, 404}, response.text
    if response.status_code != 404:
        body = response.json()
        assert body.get("id") or body.get("deployment_id") or body.get("status")
