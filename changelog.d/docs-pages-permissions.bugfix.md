Fixed the Docs workflow, which had never run. The caller granted `contents:
write` — the shape `mkdocs gh-deploy` needs — but the shared docs spine deploys
through the Pages Actions and requires `contents: read` plus `pages: write` and
`id-token: write`. All three were unmet, and an unmet request fails the run at
startup with no logs and no checks.
