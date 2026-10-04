# Legacy models archive

`archive/legacy-models/models_monolith.py` is archived reference code from the pre-split monolith.
It was moved out of `app/legacy/` so that runtime code, packaging, and type checking no longer see it.

- **Do not import** this file from any runtime, test, or tooling code.
- Use `app/models/` instead.
- `messenger.spec` does not list this file; re-adding it requires a spec review.
