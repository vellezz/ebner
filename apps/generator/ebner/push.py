"""Web Push: telling subscribers an entry has landed.

Pushes carry **no payload**. Encrypting one per subscription under RFC 8291 is
a real amount of cryptography to own for the sake of a title the service worker
can simply fetch from a static JSON file. So the push is a nudge, and the
worker asks the site what to say.

That leaves only VAPID: a signed assertion that this push came from this site.
One JWT per push origin, ES256 over P-256 — enough that `cryptography` earns
its place in the dependency list and nothing else does.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .d1 import execute, query, sql_str

SUBJECT = "mailto:bot@ebner.gripe"
# Twelve hours: comfortably inside the twenty-four the spec allows, and far
# longer than any run needs.
JWT_TTL = 12 * 3600


class PushError(RuntimeError):
    pass


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _private_key():
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError as error:  # pragma: no cover
        raise PushError("the `cryptography` package is not installed") from error

    raw = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not raw:
        raise PushError("VAPID_PRIVATE_KEY is not set")
    padded = raw + "=" * (-len(raw) % 4)
    scalar = int.from_bytes(base64.urlsafe_b64decode(padded), "big")
    return ec.derive_private_key(scalar, ec.SECP256R1())


def _public_key_bytes(key) -> bytes:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    return key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


def _vapid_header(origin: str, key) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    header = _b64(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    payload = _b64(
        json.dumps(
            {"aud": origin, "exp": int(time.time()) + JWT_TTL, "sub": SUBJECT},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()

    der = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der)
    # JWS wants the raw pair, fixed width — not the DER the library returns.
    signature = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    token = f"{header}.{payload}.{signature}"
    return f"vapid t={token}, k={_b64(_public_key_bytes(key))}"


def _send_one(endpoint: str, key) -> int:
    origin = "{0.scheme}://{0.netloc}".format(urlparse(endpoint))
    request = urllib.request.Request(
        endpoint,
        data=b"",
        method="POST",
        headers={
            "Authorization": _vapid_header(origin, key),
            "TTL": "86400",
            "Content-Length": "0",
            # Says there is no encrypted payload, which is the whole point.
            "Urgency": "normal",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def wait_for_site(day: int, *, timeout: int = 240) -> bool:
    """Wait until the published site reports the new entry.

    The push carries nothing, so the service worker reads /api/latest.json to
    decide what to say. Firing before the deploy lands would announce
    yesterday's entry with today's notification.

    Day 7 deployed in 31 seconds and this function declared the site behind
    four minutes later, twice. The cause was the request identifying itself as
    `Python-urllib/3.12` from a datacentre address, which Cloudflare declined;
    naming the caller fixed it outright.

    **Every attempt reports its outcome.** The first diagnosis was the edge
    cache — which was genuinely serving hits, and was genuinely irrelevant —
    and it survived a whole fix and a rerun because `except Exception: pass`
    discarded the only evidence that mattered. The cache-busting stayed on
    afterwards: it costs nothing and the answer must be fresh regardless.
    """
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            request = urllib.request.Request(
                f"https://ebner.gripe/api/latest.json?t={int(time.time() * 1000)}",
                headers={
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    # This line is the fix. A bare `Python-urllib/3.12` from a
                    # datacentre address was being turned away; with a real
                    # User-Agent the same poll succeeds on its first attempt.
                    "User-Agent": "ebner-bot (+https://ebner.gripe)",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8")
            latest = json.loads(body)
            found = int(latest.get("day", -1)) if latest else -1
            if found >= day:
                return True
            print(f"  poll {attempt}: site reports day {found}, waiting for {day}")
        except urllib.error.HTTPError as error:
            print(f"  poll {attempt}: HTTP {error.code} {error.reason}")
        except Exception as error:
            print(f"  poll {attempt}: {type(error).__name__}: {error}")
        time.sleep(10)
    return False


def notify(*, remote: bool = True) -> dict:
    """Push to every live subscription. Never raises on a dead one."""
    rows = query(
        "SELECT endpoint FROM push_subscriptions WHERE gone_at IS NULL", remote=remote
    )
    if not rows:
        return {"sent": 0, "gone": 0, "failed": 0, "total": 0}

    key = _private_key()
    sent = failed = 0
    gone: list[str] = []

    for row in rows:
        status = _send_one(row["endpoint"], key)
        if status in (404, 410):
            # The subscription is over: the browser dropped it or the user
            # cleared site data. Mark it rather than retry it daily forever.
            gone.append(row["endpoint"])
        elif 200 <= status < 300:
            sent += 1
        else:
            failed += 1

    if gone:
        execute(
            [
                "UPDATE push_subscriptions SET gone_at = datetime('now') "
                f"WHERE endpoint IN ({', '.join(sql_str(e) for e in gone)})"
            ],
            remote=remote,
        )

    return {"sent": sent, "gone": len(gone), "failed": failed, "total": len(rows)}
