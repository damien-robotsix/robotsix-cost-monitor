All 18 fields of the `AuthConfig`/`Settings` config models now carry
non-empty `Field(description=...)` strings, and `config/config.schema.json`
was regenerated so the deploy UI surfaces per-field help text alongside the
existing titles, defaults, and advanced flags.
