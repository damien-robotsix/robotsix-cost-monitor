#!/usr/bin/env python3
"""Validate that query parameters in route handlers are documented in _CHAT_SKILL.

Parses @router.get(...) decorators and function signatures from
src/robotsix_cost_monitor/routes.py, extracts per-route query parameters
(via ``name: type = Query(...)`` defaults), and checks that each
parameter is mentioned in the corresponding _CHAT_SKILL Markdown table
row.

Exits 0 when every query parameter is accounted for; exits 1 with a
list of missing parameters otherwise.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROUTES_PATH = Path("src/robotsix_cost_monitor/routes.py")

# Query parameters that are documented globally in the _CHAT_SKILL
# section preamble rather than on each individual table row.
GLOBALLY_DOCUMENTED_PARAMS: frozenset[str] = frozenset({"project", "hours"})


def _is_router_get(node: ast.expr) -> bool:
    """Return True when *node* is a ``router.get(...)`` call."""
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "get":
        return False
    return isinstance(node.func.value, ast.Name) and node.func.value.id == "router"


def _extract_route_path(node: ast.Call) -> str | None:
    """Extract the literal path string from ``router.get("/path")``."""
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _extract_query_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return the set of function parameters whose default is a ``Query(...)`` call."""
    params: set[str] = set()
    defaults = node.args.defaults
    num_no_default = len(node.args.args) - len(defaults)

    for i, arg in enumerate(node.args.args):
        if i < num_no_default:
            continue
        default = defaults[i - num_no_default]
        if isinstance(default, ast.Call):
            if isinstance(default.func, ast.Name) and default.func.id == "Query":
                params.add(arg.arg)

    return params


def parse_handler_query_params(source: str) -> dict[str, set[str]]:
    """Walk the AST of *source* and return ``{route_path: {param, ...}}``.

    Only includes routes decorated with ``@router.get(...)`` and only
    parameters whose *default* value is a ``Query(...)`` call.
    """
    tree = ast.parse(source)
    routes: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            if _is_router_get(decorator):
                assert isinstance(decorator, ast.Call)
                path = _extract_route_path(decorator)
                if path is not None:
                    routes[path] = _extract_query_params(node)

    return routes


def parse_chat_skill_table(source: str) -> dict[str, str]:
    """Extract the ``_CHAT_SKILL`` Markdown table rows.

    Returns ``{route_path: description_text}`` for every ``GET`` route
    listed in a ``| `GET /path` | desc |`` table row.
    """
    match = re.search(r"_CHAT_SKILL\s*=\s*\"\"\"(.+?)\"\"\"", source, re.DOTALL)
    if not match:
        print("ERROR: Could not find _CHAT_SKILL docstring", file=sys.stderr)
        sys.exit(1)

    doc = match.group(1)

    pattern = re.compile(r"\|\s*`GET\s+(/\S+?)`\s*\|\s*(.+?)\s*\|")
    table: dict[str, str] = {}
    for m in pattern.finditer(doc):
        path = m.group(1)
        desc = m.group(2).strip()
        table[path] = desc

    if not table:
        print(
            "ERROR: No GET routes found in _CHAT_SKILL table — regex may need updating",
            file=sys.stderr,
        )
        sys.exit(1)

    return table


def main() -> None:
    """Parse route handlers and _CHAT_SKILL table, then exit non-zero on mismatches."""
    if not ROUTES_PATH.exists():
        print(f"ERROR: {ROUTES_PATH} not found", file=sys.stderr)
        sys.exit(1)

    source = ROUTES_PATH.read_text()

    handler_params = parse_handler_query_params(source)
    table_descs = parse_chat_skill_table(source)

    errors: list[str] = []

    for path, params in sorted(handler_params.items()):
        if path not in table_descs:
            # Route not listed in the table — skip (e.g. /config, /settings).
            continue

        desc = table_descs[path]
        for param in sorted(params):
            if param in GLOBALLY_DOCUMENTED_PARAMS:
                continue
            param_ref = f"?{param}="
            if param_ref not in desc:
                errors.append(
                    f"  {path}: query parameter '{param}' is not documented "
                    f"in the _CHAT_SKILL table row"
                )

    if errors:
        print(
            "_CHAT_SKILL table is missing query parameter documentation:",
            file=sys.stderr,
        )
        for err in errors:
            print(err, file=sys.stderr)
        sys.exit(1)

    print("_CHAT_SKILL table is consistent with route handler signatures.")


if __name__ == "__main__":
    main()
