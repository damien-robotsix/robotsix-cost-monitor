# Continuous deployment — server.robotsix.net

This directory holds everything needed to run `robotsix-cost-monitor` on
`server.robotsix.net` as an auto-updating Docker stack reachable at
`https://cost.robotsix.net`.

How it fits together:

```
merge to main ─▶ release.yml builds & pushes ghcr.io/…/robotsix-cost-monitor:main
                                              │
                            Watchtower polls ─┘ (every 5 min) ─▶ redeploys
                                                                  cost-monitor
internet ─▶ nginx (TLS + basic auth) ─▶ 127.0.0.1:8099 ─▶ cost-monitor container
```

- **Continuous deploy:** pushing to `main` publishes a moving `:main` image
  (`../.github/workflows/release.yml`). Watchtower on the server polls GHCR and
  redeploys the `cost-monitor` container automatically.
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

### 3. Project configuration

The stack bind-mounts `./config` and `./data` (created on first run). Provide a
config file with your Langfuse projects (and optional OpenRouter keys):

```sh
mkdir -p config data
cp /tmp/rcm/config/projects.example.yaml config/projects.yaml
$EDITOR config/projects.yaml
```

To enable the optional LLM cost-analyst, fill in the `settings.analyst` block
(`model`, `base_url`, `api_key`) in `config/projects.yaml`. The image already
includes the `analyst` extra (the `openai` client), so no rebuild is needed.

### 3a. Fix bind-mount ownership

The container runs as UID 10001 (`appuser`), but files you create on the host
are owned by your login user. Give UID 10001 ownership so the container can read
its config and write runtime state (reconciliation snapshots, analyst
proposals):

```sh
sudo chown 10001:10001 config/projects.yaml
sudo chown -R 10001:10001 data
chmod 600 config/projects.yaml      # contains credentials
```

### 4. GHCR pull access (only if the package is private)

The simplest setup is to make the GHCR package **public** (GitHub → the package
→ Package settings → Change visibility → Public). Then no auth is needed and
Watchtower pulls freely.

If you keep it private, give the host a token with `read:packages` and
uncomment the `config.json` volume in `docker-compose.yml`:

```sh
echo "$GHCR_TOKEN" | docker login ghcr.io -u damien-robotsix --password-stdin
# then uncomment:  - /root/.docker/config.json:/config.json:ro
```

### 5. Start the stack

```sh
docker compose up -d
docker compose ps            # cost-monitor + watchtower should be Up
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

Watchtower redeploys automatically within ~5 min of a new `:main` image. To
force an immediate pull:

```sh
docker compose pull && docker compose up -d
```
