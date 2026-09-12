from __future__ import annotations

import argparse
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_markers(path: Path | None = None) -> dict[str, str]:
    source = path or HERE / "markers.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    markers = data.get("markers")
    if not isinstance(markers, dict) or not markers:
        raise ValueError("markers.json must contain a non-empty 'markers' object")
    result: dict[str, str] = {}
    for name, token in markers.items():
        if not isinstance(name, str) or not isinstance(token, str) or not token:
            raise ValueError("marker names and values must be non-empty strings")
        result[name] = token
    return result


def score_text(text: str, markers: dict[str, str]) -> dict[str, object]:
    presence = {name: token in text for name, token in markers.items()}
    hits = sum(presence.values())
    total = len(presence)
    return {
        "markers": presence,
        "hits": hits,
        "total": total,
        "score": hits / total if total else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score exact Context Guard benchmark markers")
    parser.add_argument("response", type=Path, help="UTF-8 file containing the post-compact probe response")
    parser.add_argument("--markers", type=Path, default=None, help="optional marker manifest")
    args = parser.parse_args()

    text = args.response.read_text(encoding="utf-8")
    result = score_text(text, load_markers(args.markers))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
