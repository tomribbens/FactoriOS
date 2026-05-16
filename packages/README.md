# Arch packages

Three PKGBUILDs:

- `factorios-launcher` — installs the Python launcher library + CLI; owns `/var/lib/factorios/` skeleton.
- `factorios-greeter` — installs the GTK4 greeter; depends on `factorios-launcher`.
- `factorios-base` — meta-package: pulls in greeter + launcher + labwc + seatd + mesa + NetworkManager, installs `factorios.service`, and in its `.install` hook creates the `factorios` system user.

Each PKGBUILD uses a `prepare()` step that copies its source tree out of the monorepo via `$startdir/../../<dir>` — no manual staging needed.

## Building

Use the top-level `build.sh`, which builds all three in dependency order and stages them into the local repo at `iso/airootfs/var/cache/factorios-repo/`:

```
./build.sh
```

To build a single package directly (no orchestration, no repo update):

```
( cd packages/factorios-launcher && makepkg -f --noconfirm --nodeps )
```

`--nodeps` is required when building greeter or base in isolation, since they depend on `factorios-launcher` which isn't published in any official repo.
