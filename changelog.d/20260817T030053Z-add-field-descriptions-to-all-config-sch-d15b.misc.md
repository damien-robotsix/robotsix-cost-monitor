Added human-readable `Field(description=...)` values to every field of the
`AuthConfig` and `Settings` config models, and regenerated
`config/config.schema.json` so the deploy UI surfaces per-field help text
alongside the existing titles, defaults, and advanced flags.
