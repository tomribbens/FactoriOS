# systemd glue

## factorios.service

One system unit on tty1, running as the `factorios` user, that execs `labwc -s /usr/bin/factorios-greeter`. labwc is a wlroots-based kiosk-friendly compositor; `-s` runs the greeter as its only client. The greeter spawns Factorio as a child of itself and waits — when the game exits, the greeter is still running, so we return to the chooser.

There is no display manager and no Unix-level login. The factorio.com greeter is the only auth.

## Why labwc, not cage

cage exits when its single app exits. The greeter needs to outlive any individual Factorio session and re-display the chooser, so we need a compositor that keeps running. labwc does, costs almost nothing, and integrates cleanly with seatd.

## seatd

labwc needs a seat. The `factorios` user is in the `seat` group; `seatd.service` is enabled by the installer.
