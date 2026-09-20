"""Workers AI: embeddings.

Wrangler has no inference command — only `ai models` and `ai finetune` — so
this is the one place that talks to the Cloudflare REST API directly, and the
one place that needs a bearer token rather than a wrangler subprocess.

Token resolution keeps `wrangler login` as the only thing a person has to do:

  1. CLOUDFLARE_API_TOKEN, which is what CI sets.
  2. The OAuth token wrangler already stored locally.

The OAuth token expires and wrangler refreshes it on its own schedule. When it
has gone stale the API answers 401 and the fix is `wrangler login`, which the
error says.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from .config import load

API = "https://api.cloudflare.com/client/v4"


class AIError(RuntimeError):
    pass


def _oauth_token_paths() -> list[Path]:
    home = Path.home()
    candidates = [
        os.environ.get("WRANGLER_CONFIG_DIR"),
        os.environ.get("APPDATA"),
        os.environ.get("XDG_CONFIG_HOME"),
    ]
    paths = []
    for base in candidates:
        if base:
            paths.append(Path(base) / "xdg.config" / ".wrangler" / "config" / "default.toml")
            paths.append(Path(base) / ".wrangler" / "config" / "default.toml")
    paths.append(home / ".config" / ".wrangler" / "config" / "default.toml")
    paths.append(home / ".wrangler" / "config" / "default.toml")
    return paths


def bearer_token() -> str:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if token:
        return token

    # Parsed with a regex rather than a TOML library: this is one flat
    # `key = "value"` line and Python 3.10 has no tomllib in the stdlib.
    for path in _oauth_token_paths():
        if not path.exists():
            continue
        match = re.search(r'^\s*oauth_token\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1)

    raise AIError(
        "no Cloudflare credential — set CLOUDFLARE_API_TOKEN or run `wrangler login`"
    )


def _post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {bearer_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:400]
        if error.code == 401:
            raise AIError(
                "Cloudflare rejected the credential (401). If this is a wrangler "
                "OAuth session it has expired — run `wrangler login`."
            ) from error
        raise AIError(f"Workers AI failed ({error.code}): {detail}") from error

    if not body.get("success", False):
        raise AIError(f"Workers AI returned errors: {body.get('errors')}")
    return body["result"]


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings.

    The model is @cf/baai/bge-m3, which is multilingual — the fragments are
    Polish prose, so an English-only embedding model would be a poor fit no
    matter how well it scored on English benchmarks.
    """
    if not texts:
        return []
    cfg = load("cloudflare.yaml")
    result = _post(
        f"/accounts/{cfg['account_id']}/ai/run/{cfg['embedding_model']}",
        {"text": texts},
    )
    vectors = result.get("data") or []
    if len(vectors) != len(texts):
        raise AIError(f"asked for {len(texts)} embeddings, got {len(vectors)}")
    expected = int(cfg["embedding_dimensions"])
    for vector in vectors:
        if len(vector) != expected:
            raise AIError(f"expected {expected} dimensions, got {len(vector)}")
    return vectors
