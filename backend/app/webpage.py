"""Fetches a public web page for a teacher and extracts its readable text (the Python counterpart of a Jsoup scrape).

The server makes the request, so it must never be usable to reach private networks or the cloud metadata server.
Every hop is checked: only http(s) on default ports, every resolved address must be public, and the connection
is made to the checked address itself so a second DNS lookup cannot swap it for an internal one.
"""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

MAX_BYTES = 2 * 1024 * 1024
MAX_TEXT = 40_000
MIN_TEXT = 200
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
HEADERS = {"User-Agent": "ElevateNotesFetcher/1.0 (+teacher notes import)", "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1"}
ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
NOISE_TAGS = ["script", "style", "noscript", "template", "svg", "canvas", "iframe", "form", "nav", "header", "footer", "aside"]


def _reject(message: str, status: int = 422) -> HTTPException:
    return HTTPException(status, message)


def _check_url(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise _reject("Enter a full web address starting with http:// or https://.")
    if parts.username or parts.password:
        raise _reject("Web addresses with a username or password are not allowed.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise _reject("That web address is not valid.") from exc
    if port not in (80, 443):
        raise _reject("Only standard web ports (80 and 443) are allowed.")
    return parts.scheme, parts.hostname, port


def _public_address(host: str, port: int) -> str:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise _reject("That web address could not be found.") from exc
    addresses = [info[4][0].split("%")[0] for info in infos]
    if not addresses or not all(ipaddress.ip_address(address).is_global for address in addresses):
        raise _reject("Only public web pages can be used.")
    return addresses[0]


async def _get(url: str) -> tuple[bytes, str, str]:
    """Follows up to MAX_REDIRECTS redirects, checking each address, and returns (body, content type, final URL)."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, headers=HEADERS) as client:
        for _ in range(MAX_REDIRECTS + 1):
            scheme, host, port = _check_url(url)
            address = await asyncio.to_thread(_public_address, host, port)
            literal = f"[{address}]" if ":" in address else address
            target = urlsplit(url)._replace(netloc=f"{literal}:{port}").geturl()
            try:
                async with client.stream("GET", target, headers={"Host": host},
                                         extensions={"sni_hostname": host}) as response:
                    if response.is_redirect and response.headers.get("location"):
                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code >= 400:
                        raise _reject(f"The page could not be opened (it answered with error {response.status_code}).")
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type not in ALLOWED_TYPES:
                        raise _reject("That link is not a web page. For PDFs, download the file and upload it instead.")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise _reject("That page is too large to import (over 2 MB).")
                    return bytes(body), content_type, url
            except httpx.TimeoutException as exc:
                raise _reject("The page took too long to answer.", 504) from exc
            except httpx.HTTPError as exc:
                raise _reject("The page could not be reached.", 502) from exc
    raise _reject("That link redirects too many times.")


def extract_text(body: bytes, content_type: str, fallback_title: str) -> tuple[str, str]:
    """Returns (title, readable text) from an HTML or plain-text body."""
    if content_type == "text/plain":
        text = body.decode("utf-8", errors="replace")
        title = fallback_title
    else:
        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        for tag in soup(NOISE_TAGS):
            tag.decompose()
        # Prefer the main article when the page marks one, otherwise use the whole body.
        root = soup.find("article") or soup.find("main") or soup.body or soup
        text = root.get_text("\n")
        title = title or fallback_title
    lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return title[:120], cleaned[:MAX_TEXT]


async def fetch_notes(url: str) -> dict:
    body, content_type, final_url = await _get(url)
    host = urlsplit(final_url).hostname or "web page"
    title, text = extract_text(body, content_type, host)
    if len(text) < MIN_TEXT:
        raise _reject("Not enough readable text was found. The page may need JavaScript or be behind a login; "
                      "paste the text into the description instead.")
    return {"url": final_url, "title": title, "text": text, "words": len(text.split())}
