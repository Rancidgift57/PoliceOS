"""
Small HS256-signed session token, deliberately hand-rolled instead of using
PyJWT. Reason: PyPI has two unrelated packages that both install a
top-level `jwt` module - PyJWT and a different package literally called
`jwt` - so `import jwt` is ambiguous depending on install order and
whatever else is on the machine. Rather than fight that, this implements
the handful of lines an HS256 JWT actually needs.

Format is a real JWT (header.payload.signature, base64url, HMAC-SHA256) so
it's still inspectable/compatible with standard tools if needed - just
produced and verified without pulling in a conflict-prone dependency.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-secret-change-me")
_ALG_HEADER = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")


class TokenError(Exception):
    pass


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def make_token(claims: Dict[str, Any], ttl_days: int = 30) -> str:
    payload = {**claims, "iat": int(time.time()), "exp": int(time.time()) + ttl_days * 86400}
    payload_b64 = _b64url(json.dumps(payload).encode())
    signing_input = _ALG_HEADER + b"." + payload_b64
    signature = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64url(signature)).decode()


def verify_token(token: str) -> Dict[str, Any]:
    try:
        header_b64, payload_b64, sig_b64 = token.encode().split(b".")
    except ValueError as exc:
        raise TokenError("Malformed token") from exc

    signing_input = header_b64 + b"." + payload_b64
    expected_sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64.decode())):
        raise TokenError("Bad signature")

    payload = json.loads(_b64url_decode(payload_b64.decode()))
    if payload.get("exp", 0) < time.time():
        raise TokenError("Token expired")
    return payload
