# Legacy package

`app/legacy/models_monolith.py` is archived reference code from the pre-split monolith.

- **Do not import** this package from runtime HTTP, socket, or service modules.
- Use `app/models/` instead.
- `messenger.spec` still lists `app.legacy.models_monolith` for packaged compatibility; removing it requires a spec review.