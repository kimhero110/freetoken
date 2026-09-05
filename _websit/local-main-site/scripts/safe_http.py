import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from numbers import Real
from urllib.parse import urljoin, urlparse

import requests


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 16 * 1024
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "x-api-key", "api-key"}


@dataclass(frozen=True)
class PinnedResponse:
    status: int
    headers: dict
    body: bytes


def resolve_public_https_url(url):
    if not isinstance(url, str) or any(ord(char) < 32 for char in url):
        raise ValueError("source URL contains invalid characters")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("only unauthenticated HTTPS URLs are allowed")
    try:
        port = parsed.port or 443
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, ValueError) as exc:
        raise ValueError(f"cannot resolve source host: {parsed.hostname}") from exc
    if not addresses:
        raise ValueError("source host resolved to no addresses")

    resolved = []
    for family, socktype, proto, _, address in addresses:
        ip = ipaddress.ip_address(address[0])
        if not ip.is_global:
            raise ValueError(f"source host resolves to a non-public address: {ip}")
        endpoint = (family, socktype, proto, str(ip))
        if endpoint not in resolved:
            resolved.append(endpoint)
    return parsed, resolved


def validate_public_https_url(url):
    resolve_public_https_url(url)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, port, endpoint, timeout):
        super().__init__(hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self._endpoint = endpoint

    def connect(self):
        family, socktype, proto, ip = self._endpoint
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(self.timeout)
        try:
            address = (ip, self.port, 0, 0) if family == socket.AF_INET6 else (ip, self.port)
            sock.connect(address)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _request_headers(headers):
    request_headers = {}
    for key, value in (headers or {}).items():
        if not isinstance(key, str) or not isinstance(value, str) or any(ord(char) < 32 for char in key + value):
            raise ValueError("request headers must be safe strings")
        if key.lower() == "host":
            raise ValueError("Host header cannot be overridden")
        request_headers[key] = value
    request_headers["Accept-Encoding"] = "identity"
    return request_headers


def _open_pinned(parsed, endpoints, method, headers, body, connect_timeout, read_timeout):
    request_headers = _request_headers(headers)
    target = parsed.path or "/"
    if parsed.query:
        target += f"?{parsed.query}"
    last_error = None
    # A POST may have reached the provider before a socket/read failure. Never
    # fail over to another address and risk duplicating a billable request.
    request_endpoints = endpoints[:1] if method == "POST" else endpoints
    for endpoint in request_endpoints:
        connection = _PinnedHTTPSConnection(parsed.hostname, parsed.port or 443, endpoint, connect_timeout)
        try:
            if body is None:
                connection.request(method, target, headers=request_headers)
            else:
                connection.request(method, target, body=body, headers=request_headers)
            if getattr(connection, "sock", None) is not None:
                connection.sock.settimeout(read_timeout)
            return connection, connection.getresponse()
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            connection.close()
            last_error = exc
    raise requests.ConnectionError(f"unable to connect to validated source host: {last_error}")


def pinned_public_https_request(
    url,
    *,
    method="GET",
    headers=None,
    body=None,
    connect_timeout=10,
    read_timeout=20,
    max_response_bytes=MAX_RESPONSE_BYTES,
    allowed_content_types=(),
    authenticated=False,
):
    """Make one bounded request to a validated, DNS-pinned public HTTPS endpoint."""
    method = method.upper()
    if method not in {"GET", "POST"}:
        raise ValueError("only GET and POST requests are supported")
    if body is not None and not isinstance(body, bytes):
        raise TypeError("request body must be bytes or null")
    if body is not None and len(body) > MAX_REQUEST_BYTES:
        raise ValueError("request body exceeds 16 KiB")
    for name, value in (("connect", connect_timeout), ("read", read_timeout)):
        if isinstance(value, bool) or not isinstance(value, Real) or not 0 < value <= 120:
            raise ValueError(f"{name} timeout must be between 0 and 120 seconds")
    if (
        isinstance(max_response_bytes, bool)
        or not isinstance(max_response_bytes, int)
        or not 0 < max_response_bytes <= MAX_RESPONSE_BYTES
    ):
        raise ValueError("response limit must be between 1 byte and 2 MiB")
    if not isinstance(allowed_content_types, (tuple, list)) or not allowed_content_types:
        raise ValueError("an explicit content type allowlist is required")
    normalized_types = tuple(value.lower() for value in allowed_content_types if isinstance(value, str) and value)
    if len(normalized_types) != len(allowed_content_types):
        raise ValueError("content type allowlist is invalid")
    request_headers = _request_headers(headers)
    has_credentials = any(key.lower() in SENSITIVE_HEADERS for key in request_headers)
    if has_credentials and not authenticated:
        raise ValueError("credential headers require authenticated=True")

    parsed, endpoints = resolve_public_https_url(url)
    connection, response = _open_pinned(
        parsed, endpoints, method, request_headers, body, connect_timeout, read_timeout
    )
    try:
        if response.status in REDIRECT_STATUSES:
            if authenticated or has_credentials:
                raise requests.TooManyRedirects("authenticated requests cannot redirect")
            raise requests.TooManyRedirects("pinned request does not follow redirects")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in normalized_types:
            raise requests.RequestException(f"unsupported content type: {content_type or 'missing'}")
        content_encoding = response.headers.get("content-encoding", "identity").lower()
        if content_encoding not in ("", "identity"):
            raise requests.RequestException(f"unsupported content encoding: {content_encoding}")
        response_body = response.read(max_response_bytes + 1)
        if len(response_body) > max_response_bytes:
            raise requests.RequestException("response exceeds configured limit")
        return PinnedResponse(
            status=response.status,
            headers={key.lower(): value for key, value in response.headers.items()},
            body=response_body,
        )
    finally:
        connection.close()


def get_public_text(url, headers=None, timeout=20, max_redirects=3):
    current = url
    current_headers = {key: value for key, value in (headers or {}).items() if key.lower() != "host"}
    for _ in range(max_redirects + 1):
        parsed, endpoints = resolve_public_https_url(current)
        connection, response = _open_pinned(parsed, endpoints, "GET", current_headers, None, timeout, timeout)
        try:
            if response.status in REDIRECT_STATUSES:
                location = response.headers.get("location")
                if not location:
                    raise requests.RequestException("redirect response has no location")
                current = urljoin(current, location)
                current_headers = {
                    key: value for key, value in current_headers.items() if key.lower() not in SENSITIVE_HEADERS
                }
                continue
            if response.status >= 400:
                raise requests.HTTPError(f"source returned HTTP {response.status}")
            content_type = response.headers.get("content-type", "").lower()
            if not any(content_type.startswith(value) for value in ALLOWED_CONTENT_TYPES):
                raise requests.RequestException(f"unsupported content type: {content_type or 'missing'}")
            content_encoding = response.headers.get("content-encoding", "identity").lower()
            if content_encoding not in ("", "identity"):
                raise requests.RequestException(f"unsupported content encoding: {content_encoding}")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise requests.RequestException("source response exceeds 2 MiB")
            encoding = response.headers.get_content_charset() or "utf-8"
            return body.decode(encoding, errors="replace")
        finally:
            connection.close()
    raise requests.TooManyRedirects(f"source exceeded {max_redirects} redirects")
