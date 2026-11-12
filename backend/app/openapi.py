"""Export the OpenAPI document (the API contract consumed by the Phase 4 frontend).

    uv run python -m app.openapi           # write backend/openapi.json
    uv run python -m app.openapi --check   # exit 1 if the committed file is out of date

The document depends only on code (no settings, secrets or timestamps), so it is reproducible.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR, Settings
from app.main import create_app

OPENAPI_FILE = BACKEND_DIR / "openapi.json"


def openapi_document() -> dict[str, Any]:
    app = create_app(Settings.model_validate({"database_url": None}))
    return app.openapi()


def render() -> str:
    return json.dumps(openapi_document(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str], path: Path = OPENAPI_FILE) -> int:
    text = render()
    if "--check" in argv:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != text:
            print(f"{path.name} is out of date: run `python -m app.openapi`", file=sys.stderr)
            return 1
        print(f"{path.name} is up to date")
        return 0
    path.write_bytes(text.encode("utf-8"))
    print(f"Wrote {path.name}")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper, tested via main()
    sys.exit(main(sys.argv[1:]))
