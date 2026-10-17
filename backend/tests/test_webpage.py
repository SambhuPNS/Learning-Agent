"""Importing teacher notes from a web page: text extraction and protection against server-side request forgery."""

import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import webpage
from app.main import app

client = TestClient(app)

PAGE = b"""<html><head><title>Photosynthesis - Notes</title><script>var x = 1;</script><style>p{}</style></head>
<body><nav>Home | About</nav><header>Site header</header>
<article><h1>Photosynthesis</h1>
<p>Plants use sunlight, water and carbon dioxide to make glucose and oxygen in a process called photosynthesis.</p>
<p>Chlorophyll in the leaves absorbs light energy, which is why leaves look green to us every day.</p>
<ul><li>Inputs: light, water, carbon dioxide</li><li>Outputs: glucose and oxygen</li></ul></article>
<aside>Related links</aside><footer>Copyright</footer></body></html>"""


def teacher_headers() -> dict:
    res = client.post("/api/auth/signup", json={"name": "Web Teacher", "email": "web.teacher@example.com",
                                                "password": "secret123", "role": "teacher"})
    if res.status_code != 200:
        res = client.post("/api/auth/login", json={"email": "web.teacher@example.com", "password": "secret123"})
    return {"Authorization": f"Bearer {res.json()['token']}"}


def test_extracts_article_text_without_page_chrome():
    title, text = webpage.extract_text(PAGE, "text/html", "example.org")
    assert title == "Photosynthesis - Notes"
    assert "Chlorophyll in the leaves" in text and "Outputs: glucose and oxygen" in text
    for noise in ("var x", "Home | About", "Site header", "Related links", "Copyright"):
        assert noise not in text


def test_plain_text_pages_are_used_as_they_are():
    title, text = webpage.extract_text(b"Line one\n\n  Line   two  \n", "text/plain", "example.org")
    assert title == "example.org" and text == "Line one\nLine two"


@pytest.mark.parametrize("url", [
    "ftp://example.org/file", "file:///etc/passwd", "javascript:alert(1)", "example.org", "http://user:pw@example.org/",
    "http://example.org:8080/", "http://example.org:22/",
])
def test_unsafe_or_malformed_addresses_are_refused(url):
    with pytest.raises(HTTPException) as err:
        webpage._check_url(url)
    assert err.value.status_code == 422


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "0.0.0.0", "::1"])
def test_private_and_metadata_addresses_are_refused(host):
    with pytest.raises(HTTPException) as err:
        webpage._public_address(host, 80)
    assert err.value.status_code == 422


def test_a_local_server_cannot_be_reached_through_the_importer():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *args):
            pass

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(HTTPException) as err:
            asyncio.run(webpage.fetch_notes(f"http://127.0.0.1:{port}/"))
        assert err.value.status_code == 422
    finally:
        server.shutdown()


def test_endpoint_returns_notes_and_requires_a_teacher(monkeypatch):
    async def fake_get(url):
        return PAGE, "text/html", url

    monkeypatch.setattr(webpage, "_get", fake_get)
    assert client.post("/api/teacher/topics/fetch-url", json={"url": "https://example.org/p"}).status_code == 401
    res = client.post("/api/teacher/topics/fetch-url", headers=teacher_headers(), json={"url": "https://example.org/p"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["title"] == "Photosynthesis - Notes" and data["words"] > 20 and "glucose" in data["text"]


def test_pages_with_too_little_text_are_explained(monkeypatch):
    async def fake_get(url):
        return b"<html><body><div id='app'></div><script>render()</script></body></html>", "text/html", url

    monkeypatch.setattr(webpage, "_get", fake_get)
    res = client.post("/api/teacher/topics/fetch-url", headers=teacher_headers(), json={"url": "https://example.org/spa"})
    assert res.status_code == 422 and "JavaScript" in res.json()["detail"]
