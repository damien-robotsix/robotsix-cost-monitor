# CLI Reference

`robotsix-cost-monitor` provides three subcommands: **serve**, **summary**, and
**reconcile**. All subcommands load the JSON configuration from the path set by
`ROBOTSIX_CONFIG_FILE` (or `config/config.json` by default).

---

## `robotsix-cost-monitor serve`

Start the dashboard web server.

```console
$ robotsix-cost-monitor serve --help
Usage: robotsix-cost-monitor serve [OPTIONS]

  Run the dashboard web server.

Options:
  --host  TEXT  [default: 127.0.0.1]
  --port  INT   [default: 8099]
  --help        Show this message and exit.
```

| Option | Type | Default | Description |
|---|---|---|---|
| `--host` | `str` | `127.0.0.1` | Host address to bind the server to. |
| `--port` | `int` | `8099` | TCP port to listen on. |

The server uses Uvicorn with the app factory `robotsix_cost_monitor.app:create_app`.

---

## `robotsix-cost-monitor summary`

Print a per-project cost summary as JSON to stdout.

```console
$ robotsix-cost-monitor summary --help
Usage: robotsix-cost-monitor summary [OPTIONS]

  Print cost summary as JSON.

Options:
  --project TEXT  Project slug or "all" (default).  [default: all]
  --hours INT     Look-back window in hours (0 = settings default).  [default: 0]
  --help          Show this message and exit.
```

| Option | Type | Default | Description |
|---|---|---|---|
| `--project` | `str` | `"all"` | Project slug to query, or `"all"` for every configured project. |
| `--hours` | `int` | `0` | Look-back window in hours. When `0` (the default), the value of `settings.default_window_hours` from the config file is used. |

---

## `robotsix-cost-monitor reconcile`

Run OpenRouter ↔ Langfuse cost reconciliation for one or all projects.

```console
$ robotsix-cost-monitor reconcile --help
Usage: robotsix-cost-monitor reconcile [OPTIONS]

  Run OpenRouter↔Langfuse reconciliation.

Options:
  --project TEXT  Project slug or "all" (default).  [default: all]
  --help          Show this message and exit.
```

| Option | Type | Default | Description |
|---|---|---|---|
| `--project` | `str` | `"all"` | Project slug to reconcile, or `"all"` to reconcile every configured project that has an OpenRouter key. |

Reconciliation snapshots are saved under `<data_dir>/reconcile/<slug>.json` (where
`data_dir` is `settings.data_dir` from the config file, defaulting to `.data`).

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ROBOTSIX_CONFIG_FILE` | `config/config.json` | Path to the JSON configuration file. |

Log format, log level, and data directory are now configured via `settings.log_format`,
`settings.log_level`, and `settings.data_dir` in the config file.
