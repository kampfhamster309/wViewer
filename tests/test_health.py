from fastapi.testclient import TestClient
from wviewer.app import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_serves_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "wViewer" in response.text


def test_index_references_leaflet():
    response = client.get("/")
    assert "leaflet.css" in response.text
    assert "leaflet.js" in response.text


def test_index_references_app_js():
    response = client.get("/")
    assert "app.js" in response.text


def test_static_leaflet_js_served():
    response = client.get("/static/lib/leaflet/leaflet.js")
    assert response.status_code == 200


def test_static_markercluster_js_served():
    response = client.get("/static/lib/markercluster/leaflet.markercluster.js")
    assert response.status_code == 200


def test_static_style_css_served():
    response = client.get("/static/style.css")
    assert response.status_code == 200


def test_static_app_js_served():
    response = client.get("/static/app.js")
    assert response.status_code == 200
