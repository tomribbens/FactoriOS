#!/bin/bash
# Runs on autologin in the live ISO (archiso ships a bash profile that execs
# /root/.automated_script.sh if present). Kicks off the FactoriOS installer.
if [[ "$(tty)" == "/dev/tty1" ]]; then
    echo
    echo "Welcome to FactoriOS."
    echo "Bring up your network if needed (e.g. nmtui), then run: factorios-install"
    echo
    # Auto-run if the network looks up.
    if ping -c1 -W2 archlinux.org >/dev/null 2>&1; then
        /usr/local/bin/factorios-install
    fi
fi
