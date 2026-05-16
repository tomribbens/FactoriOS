# factorios-launcher

Pure-Python library + small CLI for factorio.com auth, downloads, and managing installed Factorio versions and per-user profiles. No UI, no GTK.

The greeter depends on this; future tooling (headless server provisioning, scripted reinstalls, etc.) should too.

## Modules

- `auth` — CSRF-scraped form login against `factorio.com/login`, session serialization for Remember Me.
- `download` — authenticated binary download, `latest-releases` API.
- `versions` — install/list/remove versions under `/var/lib/factorios/versions/`.
- `profiles` — per-user profile directories, `launch()` to spawn Factorio with `--write-data` pointed at a profile.
- `paths` — the single source of truth for on-disk layout. Don't hard-code paths elsewhere.

## CLI

```
factorios-launcher releases                  # public latest-releases JSON
factorios-launcher login <username>          # prompts password, caches session
factorios-launcher install <user> <version>  # e.g. 1.1.110 or latest
factorios-launcher list                      # installed versions
```

In development without install:

```
PYTHONPATH=launcher python -m factorios_launcher releases
```

## Tests

None yet. The login flow needs real factorio.com credentials to exercise end-to-end.
