"""Private single-owner hosting and durable admission limits; local modes stay open."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse

COOKIE = "__Host-sidekick-session"
ITERATIONS = 600_000
LOGIN_LIMIT = 20
LOGIN_WINDOW = 3600


def hashPassword(password: str) -> str:
    if not isinstance(password, str) or not 12 <= len(password.encode()) <= 1024:
        raise ValueError("Use a password between 12 and 1024 UTF-8 bytes")
    salt = secrets.token_bytes(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"v1$pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def passwordParts(value):
    try:
        version, algorithm, iterations, salt, digest = value.split("$")
        count = int(iterations)
        if (version != "v1" or algorithm != "pbkdf2_sha256" or not ITERATIONS <= count <= 2_000_000
                or not re.fullmatch(r"[0-9a-f]{32}", salt) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError
        return count, bytes.fromhex(salt), digest
    except (ValueError, AttributeError):
        raise ValueError("Invalid hosted password hash; create one with hashPassword") from None


def validateHosted(settings):
    configured = (settings.hosted_owner, settings.hosted_origin, settings.hosted_password_hash)
    if not any(configured):
        return
    if not all(configured) or settings.mode != "full":
        raise ValueError("Hosted access requires full mode, owner, HTTPS origin and password hash")
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", settings.hosted_owner):
        raise ValueError("Hosted owner must be a simple identifier of at most 64 characters")
    try:
        origin = urlsplit(settings.hosted_origin)
        port = origin.port
    except ValueError:
        raise ValueError("Hosted origin must be an HTTPS origin without a path") from None
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.path or origin.query or origin.fragment or port == 0
            or origin.netloc != origin.netloc.lower() or any(c.isspace() for c in origin.netloc)):
        raise ValueError("Hosted origin must be an HTTPS origin without credentials, path, query or fragment")
    host = origin.hostname
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise ValueError("Hosted origin must have a valid hostname") from None
    elif not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise ValueError("Hosted origin must have a valid hostname")
    if origin.netloc.endswith(":"):
        raise ValueError("Hosted origin must have a valid port")
    if port == 443:
        settings.hosted_origin = "https://" + origin.netloc.rsplit(":", 1)[0]
    passwordParts(settings.hosted_password_hash)
    for name, maximum in (("hosted_max_calls", 10_000), ("hosted_max_completion_tokens", 100_000_000),
            ("hosted_max_searches", 10_000), ("hosted_max_mutations", 10_000)):
        value = getattr(settings, name)
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be an integer between 0 and {maximum}")
    if type(settings.hosted_max_upload_bytes) is not int or not 1 <= settings.hosted_max_upload_bytes <= 25 * 1024 * 1024:
        raise ValueError("Hosted upload limit must be between 1 byte and 25 MiB")
    if type(settings.hosted_session_seconds) is not int or not 1 <= settings.hosted_session_seconds <= 28800:
        raise ValueError("Hosted sessions must expire within eight hours")


class HostedAccess:
    def __init__(self, settings):
        self.settings = settings
        self.path = settings.artifacts_dir / "hosted.sqlite3"
        self.credential = hashlib.sha256(settings.hosted_password_hash.encode()).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS owner(id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL, credential TEXT NOT NULL)")
            row = db.execute("SELECT name,credential FROM owner WHERE id=1").fetchone()
            if row and row[0] != settings.hosted_owner:
                raise ValueError("This persistent workspace belongs to a different hosted owner")
            db.execute("CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL NOT NULL, credential TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS usage(day TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0, searches INTEGER NOT NULL DEFAULT 0, mutations INTEGER NOT NULL DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS login_attempts(window INTEGER PRIMARY KEY, attempts INTEGER NOT NULL)")
            if not row:
                db.execute("INSERT INTO owner VALUES(1,?,?)", (settings.hosted_owner, self.credential))
            elif row[1] != self.credential:
                db.execute("DELETE FROM sessions")
                db.execute("UPDATE owner SET credential=? WHERE id=1", (self.credential,))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def authenticated(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return False
        with self.connection() as db:
            row = db.execute("SELECT expires,credential FROM sessions WHERE token=?", (self.tokenHash(token),)).fetchone()
            current = db.execute("SELECT credential FROM owner WHERE id=1").fetchone()
        return bool(row and row[0] > time.time() and row[1] == self.credential == current[0])

    @staticmethod
    def tokenHash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def login(self, username, password):
        # Reserve before PBKDF2, globally and durably, so parallel failed attempts cannot evade the cap.
        now = time.time()
        window = int(now // LOGIN_WINDOW)
        with self.transaction() as db:
            db.execute("DELETE FROM login_attempts WHERE window < ?", (window - 1,))
            db.execute("INSERT OR IGNORE INTO login_attempts VALUES(?,0)", (window,))
            recent = db.execute("SELECT COALESCE(SUM(attempts),0) FROM login_attempts").fetchone()[0]
            if recent >= LOGIN_LIMIT:
                return None, 429
            db.execute("UPDATE login_attempts SET attempts=attempts+1 WHERE window=?", (window,))
        count, salt, expected = passwordParts(self.settings.hosted_password_hash)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, count).hex()
        valid = hmac.compare_digest(digest, expected) & hmac.compare_digest(username.encode(), self.settings.hosted_owner.encode())
        if not valid:
            return None, 401
        token = secrets.token_urlsafe(32)
        with self.transaction() as db:
            current = db.execute("SELECT credential FROM owner WHERE id=1").fetchone()[0]
            if current != self.credential:
                return None, 401
            db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
            # Bound storage even if a client discards every cookie.
            db.execute("DELETE FROM sessions WHERE token IN (SELECT token FROM sessions ORDER BY expires DESC LIMIT -1 OFFSET 19)")
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (self.tokenHash(token), now + self.settings.hosted_session_seconds, self.credential))
        return token, 200

    def logout(self, token):
        if token:
            with self.transaction() as db:
                db.execute("DELETE FROM sessions WHERE token=?", (self.tokenHash(token),))

    def reserve(self, *, calls=0, tokens=0, searches=0, mutations=0):
        limits = (self.settings.hosted_max_calls, self.settings.hosted_max_completion_tokens,
            self.settings.hosted_max_searches, self.settings.hosted_max_mutations)
        requested = (calls, tokens, searches, mutations)
        if any(type(value) is not int or value < 0 for value in requested):
            raise ValueError("Invalid hosted budget reservation")
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO usage(day) VALUES(?)", (day,))
            used = db.execute("SELECT calls,tokens,searches,mutations FROM usage WHERE day=?", (day,)).fetchone()
            if any(current + amount > limit for current, amount, limit in zip(used, requested, limits, strict=True)):
                raise ValueError("Hosted daily allowance exhausted; contact the workspace operator")
            db.execute("UPDATE usage SET calls=calls+?,tokens=tokens+?,searches=searches+?,mutations=mutations+? WHERE day=?", (*requested, day))

    def budgets(self):
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self.connection() as db:
            used = db.execute("SELECT calls,tokens,searches,mutations FROM usage WHERE day=?", (day,)).fetchone() or (0, 0, 0, 0)
        limits = (self.settings.hosted_max_calls, self.settings.hosted_max_completion_tokens,
            self.settings.hosted_max_searches, self.settings.hosted_max_mutations)
        return dict(zip(("calls", "completionTokens", "searches", "mutations"),
            (max(0, limit - current) for current, limit in zip(used, limits, strict=True)), strict=True))


def accessFor(settings):
    # One process-local cache per Settings, never shared across owners or volumes.
    access = getattr(settings, "_hostedAccess", None)
    if access is None:
        access = HostedAccess(settings)
        settings._hostedAccess = access
    return access


def reserveInference(settings, tokens):
    if getattr(settings, "hosted_owner", ""):
        accessFor(settings).reserve(calls=1, tokens=tokens)


def reserveSearch(settings):
    if getattr(settings, "hosted_owner", ""):
        accessFor(settings).reserve(searches=1)


def sessionState(settings, authenticated=False):
    if not settings.hosted:
        return {"required": False, "authenticated": True, "owner": None, "budgets": None}
    return {"required": True, "authenticated": authenticated,
        "owner": settings.hosted_owner if authenticated else None,
        "budgets": accessFor(settings).budgets() if authenticated else None}


class HostedMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # No websocket API is supported; do not admit an alternate anonymous surface.
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        path, method = request.url.path, request.method

        async def respond(payload, status=200):
            await JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})(scope, receive, send)

        if path == "/api/health" and method == "GET":
            # Public liveness discloses no stored data, source fingerprints or deployment details.
            if scope.get("scheme") != "https" or request.headers.get("host") != urlsplit(self.settings.hosted_origin).netloc:
                return await respond({"status": "ok", "requires_sign_in": True})
        elif scope.get("scheme") != "https" or request.headers.get("host") != urlsplit(self.settings.hosted_origin).netloc:
            return await respond({"detail": "Use the configured HTTPS workspace origin"}, 400)
        access = accessFor(self.settings)
        token = request.cookies.get(COOKIE, "")
        authenticated = access.authenticated(token)
        if path == "/api/health" and method == "GET" and not authenticated:
            return await respond({"status": "ok", "requires_sign_in": True})
        if path == "/api/session" and method == "GET":
            return await respond(sessionState(self.settings, authenticated))
        login = path == "/api/session/login" and method == "POST"
        logout = path == "/api/session/logout" and method == "POST"
        mutation = method not in {"GET", "HEAD", "OPTIONS"}
        private = path == "/api" or path.startswith("/api/") or path.startswith(("/docs", "/redoc", "/openapi", "/exports"))
        if (private or mutation) and not authenticated and not (login or logout):
            return await respond({"detail": "Sign in to this workspace"}, 401)
        if mutation:
            if request.headers.get("origin") != self.settings.hosted_origin or request.headers.get("x-sidekick-request") != "1":
                return await respond({"detail": "Use the same-origin Sidekick website"}, 400)
            limit = 8192 if login or logout else self.settings.hosted_max_upload_bytes
            length = request.headers.get("content-length")
            if length is not None and (not length.isdigit() or len(length) > 10 or int(length) > limit):
                return await respond({"detail": "Request body exceeds its hosted limit"}, 413)
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > limit:
                    return await respond({"detail": "Request body exceeds its hosted limit"}, 413)
                if not message.get("more_body", False):
                    break
            if login:
                try:
                    payload = json.loads(body)
                    username, password = payload["username"], payload["password"]
                    if (not isinstance(username, str) or not isinstance(password, str)
                            or len(username.encode()) > 64 or not 1 <= len(password.encode()) <= 1024):
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    return await respond({"detail": "Supply a username and password"}, 400)
                token, status = access.login(username, password)
                if not token:
                    return await respond({"detail": "Sign-in unavailable; check credentials or retry later"}, status)
                response = JSONResponse(sessionState(self.settings, True), headers={"Cache-Control": "no-store"})
                response.set_cookie(COOKIE, token, max_age=self.settings.hosted_session_seconds, secure=True, httponly=True, samesite="strict", path="/")
                return await response(scope, receive, send)
            if logout:
                access.logout(token)
                response = JSONResponse(sessionState(self.settings), headers={"Cache-Control": "no-store"})
                response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="strict", path="/")
                return await response(scope, receive, send)
            if private:
                try:
                    access.reserve(mutations=1)
                except ValueError as exc:
                    return await respond({"detail": str(exc)}, 429)
            sent = False

            async def replayBody():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()
        else:
            replayBody = receive

        async def privateSend(message):
            if message["type"] == "http.response.start":
                message["headers"] = [(k, v) for k, v in message["headers"] if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)
        return await self.app(scope, replayBody, privateSend)
