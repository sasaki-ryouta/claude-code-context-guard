from __future__ import annotations

import argparse
import ast
import importlib
import json
import sys
from pathlib import Path


def _check(name: str, fn, results: dict[str, dict[str, object]]) -> None:
    try:
        fn()
    except Exception as exc:  # benchmark result, not a test-framework crash
        results[name] = {"pass": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        results[name] = {"pass": True, "error": None}


def evaluate(target: Path) -> dict[str, object]:
    target = target.resolve()
    src = target / "src"
    if not src.is_dir():
        raise SystemExit(f"target has no src directory: {src}")

    sys.path.insert(0, str(src))
    for name in list(sys.modules):
        if name == "routeforge" or name.startswith("routeforge."):
            del sys.modules[name]

    model = importlib.import_module("routeforge.model")
    parse = importlib.import_module("routeforge.parse")
    route = importlib.import_module("routeforge.route")
    cache = importlib.import_module("routeforge.cache")
    export = importlib.import_module("routeforge.export")

    Event = model.Event
    results: dict[str, dict[str, object]] = {}

    def case_sensitive_legacy_b() -> None:
        event = parse.parse_legacy_b(
            {"account": "Tenant", "id": "CaseID", "kind": "CREATED", "payload": {}}
        )
        assert event.external_id == "CaseID", event.external_id
        assert event.event_type == "created", event.event_type

    def empty_account_rejected() -> None:
        try:
            parse.parse_legacy_b(
                {"account": "  ", "id": "CaseID", "kind": "created", "payload": {}}
            )
        except ValueError:
            return
        raise AssertionError("legacy-B accepted an empty account")

    def stable_equal_routing_key() -> None:
        first = Event("Tenant", "CaseID", "created", {"timestamp": 20, "seq": "first"})
        second = Event("Tenant", "CaseID", "created", {"timestamp": 10, "seq": "second"})
        routed = route.route_events([first, second])
        assert routed == [first, second], routed

    def cache_preserves_identifier_case() -> None:
        event = Event("Tenant", "CaseID", "created", {})
        assert cache.cache_key(event) == "Tenant|CaseID|created"

    def export_preserves_identifier_case_and_shape() -> None:
        event = Event("Tenant", "CaseID", "created", {"x": 1})
        rows = export.export_records([event])
        assert rows == [
            {"tenant": "Tenant", "id": "CaseID", "type": "created", "payload": {"x": 1}}
        ], rows

    def parsers_do_not_construct_event_directly() -> None:
        tree = ast.parse((src / "routeforge" / "parse.py").read_text(encoding="utf-8"))
        direct = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Event"
        ]
        assert not direct, "parse.py still constructs Event directly"

    def exporter_has_no_identity_normalization() -> None:
        tree = ast.parse((src / "routeforge" / "export.py").read_text(encoding="utf-8"))
        forbidden = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in {"lower", "strip"}:
                forbidden.append(node.func.attr)
        assert not forbidden, f"export.py still normalizes identity fields: {forbidden}"

    checks = {
        "legacy_b_preserves_identifier_case": case_sensitive_legacy_b,
        "legacy_b_rejects_empty_account": empty_account_rejected,
        "equal_routing_keys_are_stable": stable_equal_routing_key,
        "cache_preserves_identifier_case": cache_preserves_identifier_case,
        "export_preserves_case_and_shape": export_preserves_identifier_case_and_shape,
        "parsers_use_canonical_boundary": parsers_do_not_construct_event_directly,
        "exporter_does_not_renormalize": exporter_has_no_identity_normalization,
    }
    for name, fn in checks.items():
        _check(name, fn, results)

    passed = all(item["pass"] for item in results.values())
    return {"pass": passed, "checks": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixture-v1 hidden evaluator")
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    result = evaluate(args.target)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
