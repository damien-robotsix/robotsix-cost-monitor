# Continuous deployment — server.robotsix.net

This directory holds everything needed to run `robotsix-cost-monitor` on
`server.robotsix.net` as a Docker stack reachable at
`https://cost.robotsix.net`.

How it fits together:

```
merge to main ─▶ release.yml builds & pushes ghcr.io/…/robotsix-cost-monitor:main
                                              │
                            central-deploy ───┘ (button-triggered) ─▶ redeploys
                                                                      cost-monitor
internet ─▶ nginx (TLS + basic auth) ─▶ 127.0.0.1:8099 ─▶ cost-monitor container
```

- **Continuous deploy:** pushing to `main` publishes a moving `:main` image
  (`../.github/workflows/release.yml`). Central-deploy triggers redeployment
  on demand (button in the central-deploy dashboard) instead of Watchtower
  polling every 5 minutes.
- **Ingress:** the dashboard binds to `127.0.0.1:8099` only. The host's shared
  nginx terminates TLS and enforces HTTP basic auth for `cost.robotsix.net`,
  then proxies to it. The dashboard has **no auth of its own**.

Versioned `v*` tags still publish semver + `latest` images; pin `IMAGE_TAG` in
`.env` to a version to freeze deploys instead of tracking `main`.

---

## One-time server setup

Run these on `server.robotsix.net`.

### 1. Place this stack on the host

```sh
sudo mkdir -p /opt/robotsix-cost-monitor
git clone https://github.com/damien-robotsix/robotsix-cost-monitor.git /tmp/rcm
cp -r /tmp/rcm/deploy/* /opt/robotsix-cost-monitor/
cd /opt/robotsix-cost-monitor
```

### 2. Environment file

```sh
cp .env.example .env
$EDITOR .env          # IMAGE_TAG, MONITOR_PORT
```

### 3. Provision configuration

The stack uses **named volumes** (`cost_monitor_config`, `cost_monitor_data`)
managed by the central-deploy system. Provide a config file on first deploy:

```sh
# Create the config named volume and copy the example config into it.
docker volume create cost_monitor_config
docker run --rm \
  -v cost_monitor_config:/data \
  -v /tmp/rcm/config/projects.example.yaml:/src/projects.example.yaml:ro \
  alpine cp /src/projects.example.yaml /data/projects.yaml

# Create the data volume for runtime state.
docker volume create cost_monitor_data
```

Set ownership so the container (UID 1001, `app`) can read config and write
runtime data:

```sh
docker run --rm -v cost_monitor_config:/data alpine chown -R 1001:1001 /data
docker run --rm -v cost_monitor_data:/data alpine chown -R 1001:1001 /data
```

Then edit the config:

```sh
docker run --rm -it -v cost_monitor_config:/data alpine vi /data/projects.yaml
```

To enable the optional LLM cost-analyst, fill in the `settings.analyst` block
in `projects.yaml`. The image already includes the `analyst` extra.

### 4. GHCR pull access (only if the package is private)

The simplest setup is to make the GHCR package **public** (GitHub → the package
→ Package settings → Change visibility → Public). Then no auth is needed.

If you keep it private, give the host a token with `read:packages`:

```sh
echo "$GHCR_TOKEN" | docker login ghcr.io -u damien-robotsix --password-stdin
```

### 5. Start the stack

```sh
docker compose up -d
docker compose ps            # cost-monitor should be Up
docker compose logs -f cost-monitor
```

The dashboard is now on `127.0.0.1:8099`. It is **not** yet reachable from the
internet — put it behind the shared host nginx with TLS + basic auth for
`cost.robotsix.net` (same pattern as the other robotsix services).

---

## One-shot commands

```sh
docker compose run --rm cost-monitor summary --hours 24
docker compose run --rm cost-monitor reconcile
```

## Updating

Use the central-deploy dashboard button to trigger a redeploy. To force an
immediate manual pull:

```sh
docker compose pull && docker compose up -d
```

## Migrating from bind-mounts to named volumes

If you previously relied on bind-mounted host directories (`./config` and
`./data`) and need to preserve existing data, copy the contents into the new
named volumes before bringing up the stack for the first time.

```sh
# Create named volumes (stack name prefix matches docker-compose.yml `name:`)
docker volume create robotsix-cost-monitor_cost_monitor_config
docker volume create robotsix-cost-monitor_cost_monitor_data

# Copy existing bind-mount config into the named volume
docker run --rm \
  -v "$(pwd)/config":/src:ro \
  -v robotsix-cost-monitor_cost_monitor_config:/dst \
  alpine sh -c "cp -a /src/. /dst/"

# Copy existing bind-mount data into the named volume
docker run --rm \
  -v "$(pwd)/data":/src:ro \
  -v robotsix-cost-monitor_cost_monitor_data:/dst \
  alpine sh -c "cp -a /src/. /dst/"

# Bring the new stack up
docker compose -f deploy/docker-compose.yml up -d
```

After the migration, the stack can be started with `docker compose up -d` and
the old bind-mount directories can be removed once you have verified the
service runs correctly against the named volumes.
