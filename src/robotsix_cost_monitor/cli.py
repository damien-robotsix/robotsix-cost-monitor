"""Command-line entrypoint: run the dashboard server, or print a cost summary."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import uvicorn

from .config import load_config
from .reconcile import reconcile_project
from .service import CostService


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: dispatch to serve, summary, or reconcile."""
    parser = argparse.ArgumentParser(prog="robotsix-cost-monitor")
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="run the dashboard web server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8099)

    summary = sub.add_parser("summary", help="print a cost summary as JSON")
    summary.add_argument("--project", default="all")
    summary.add_argument("--hours", type=int, default=0)

    recon = sub.add_parser("reconcile", help="run OpenRouter↔Langfuse reconciliation")
    recon.add_argument("--project", default="all")

    args = parser.parse_args(argv)

    if args.cmd == "serve" or args.cmd is None:
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8099)
        uvicorn.run(
            "robotsix_cost_monitor.app:create_app",
            host=host,
            port=port,
            factory=True,
            log_config=None,  # respect the dictConfig already applied by create_app
        )
        return 0

    cfg = load_config()
    if args.cmd == "summary":
        svc = CostService(cfg)
        h = args.hours or cfg.settings.default_window_hours
        out = asyncio.run(svc.summary(args.project, h))
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "reconcile":
        targets = (
            cfg.projects
            if args.project == "all"
            else [p for p in cfg.projects if p.slug == args.project]
        )
        recon_rows = [asyncio.run(reconcile_project(p, cfg.settings)) for p in targets]
        print(json.dumps(recon_rows, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
