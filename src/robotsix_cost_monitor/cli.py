"""Command-line entrypoint: run the dashboard server, or print a cost summary."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import uvicorn

from .clients.registry import RegistryClient
from .config import load_config, resolve_registry_api_key
from .reconcile import reconcile_all, reconcile_project
from .service import CostService


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: dispatch to serve, summary, or reconcile."""
    parser = argparse.ArgumentParser(prog="robotsix-cost-monitor")
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="run the dashboard web server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    summary = sub.add_parser("summary", help="print a cost summary as JSON")
    summary.add_argument("--project", default="all")
    summary.add_argument("--hours", type=int, default=0)

    recon = sub.add_parser("reconcile", help="run OpenRouter↔Langfuse reconciliation")
    recon.add_argument("--project", default="all")

    args = parser.parse_args(argv)

    if args.cmd == "serve" or args.cmd is None:
        cfg = load_config()
        host_val: str | None = getattr(args, "host", None)
        port_val: int | None = getattr(args, "port", None)
        host = host_val if host_val is not None else cfg.settings.server_host
        port = port_val if port_val is not None else cfg.settings.server_port
        uvicorn.run(
            "robotsix_cost_monitor.app:create_app",
            host=host,
            port=port,
            factory=True,
            log_config=None,  # respect the dictConfig already applied by create_app
        )
        return 0

    cfg = load_config()
    registry = RegistryClient(
        base_url=cfg.settings.registry_base_url,
        api_key=resolve_registry_api_key(cfg.settings),
    )
    if args.cmd == "summary":
        svc = CostService(cfg, registry)
        if cfg.settings.registry_base_url:
            asyncio.run(svc.refresh_projects())
        h = args.hours or cfg.settings.default_window_hours
        out = asyncio.run(svc.summary(args.project, h))
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "reconcile":
        svc = CostService(cfg, registry)
        if cfg.settings.registry_base_url:
            asyncio.run(svc.refresh_projects())
        if args.project == "all":
            out = asyncio.run(reconcile_all(cfg, svc))
            print(json.dumps(out, indent=2))
        else:
            projects = [p for p in svc._project_map.values() if p.slug == args.project]
            recon_rows = [
                asyncio.run(reconcile_project(p, cfg.settings)) for p in projects
            ]
            print(json.dumps(recon_rows, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
