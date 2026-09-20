"""D1 access.

Transport is the wrangler CLI rather than the REST API, for one reason: it
authenticates from an OAuth session locally and from CLOUDFLARE_API_TOKEN in
CI, so there is one auth path instead of two.

The cost is real and has to be handled carefully: `wrangler d1 execute` takes
literal SQL with no parameter binding, and everything written here is
LLM-generated Polish prose full of apostrophes. Every value goes through
`sql_str`, which is the only place a literal is built.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

REPO = Path(__file__).resolve().parents[3]

# The package's real entry point, not the .bin shim. The shim is an
# extensionless shell script, which Windows cannot execute as a process
# (WinError 193), and its .CMD sibling only exists there. Going through node
# behaves identically on Windows, in WSL and on a CI runner.
WRANGLER_JS = REPO / "apps" / "site" / "node_modules" / "wrangler" / "bin" / "wrangler.js"
NODE = os.environ.get("NODE", "node")

DB_CONFIG = REPO / "db" / "wrangler.jsonc"
DB_NAME = "ebner"


class D1Error(RuntimeError):
    pass


def sql_str(value: object) -> str:
    """Render a Python value as a SQLite literal.

    SQLite string literals have exactly one escape: a single quote is doubled.
    There are no backslash escapes, so this transformation is complete rather
    than merely careful — which is what makes hand-built SQL tolerable here.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise D1Error("floats are not used in this schema; refusing to guess a format")
    text = str(value)
    if "\x00" in text:
        raise D1Error("NUL byte in value")
    return "'" + text.replace("'", "''") + "'"


def _run(args: list[str]) -> str:
    if not WRANGLER_JS.exists():
        raise D1Error(f"wrangler not found at {WRANGLER_JS} — run `pnpm install` in apps/site")
    result = subprocess.run(
        [NODE, str(WRANGLER_JS), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO,
    )
    if result.returncode != 0:
        raise D1Error(f"wrangler failed ({result.returncode}):\n{result.stderr or result.stdout}")
    return result.stdout


def execute(statements: list[str], *, remote: bool = True) -> None:
    """Run statements as one batch.

    They go through a file rather than --command because a batch is applied
    together, and because the SQL routinely exceeds what a command line will
    carry once an entry's body is in it.
    """
    statements = [s for s in statements if s.strip()]
    if not statements:
        return

    script = ";\n".join(s.rstrip().rstrip(";") for s in statements) + ";\n"
    with NamedTemporaryFile(
        "w", suffix=".sql", delete=False, encoding="utf-8", newline="\n"
    ) as handle:
        handle.write(script)
        path = Path(handle.name)

    try:
        _run(
            [
                "d1",
                "execute",
                DB_NAME,
                "--remote" if remote else "--local",
                "-c",
                str(DB_CONFIG),
                "--file",
                str(path),
                "-y",
            ]
        )
    finally:
        path.unlink(missing_ok=True)


def query(sql: str, *, remote: bool = True) -> list[dict]:
    """Run one read and return its rows."""
    output = _run(
        [
            "d1",
            "execute",
            DB_NAME,
            "--remote" if remote else "--local",
            "-c",
            str(DB_CONFIG),
            "--json",
            "--command",
            sql,
        ]
    )
    start = output.find("[")
    if start == -1:
        raise D1Error(f"no JSON in wrangler output:\n{output}")
    payload = json.loads(output[start:])
    return payload[0].get("results", [])
