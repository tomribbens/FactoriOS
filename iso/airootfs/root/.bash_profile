# Run on every bash login. agetty autologs root on tty1 (see
# autologin.conf), so this is what greets the user and kicks off the
# installer. On other ttys we leave the user with a normal shell.
if [[ "$(tty)" == "/dev/tty1" ]]; then
    cat <<'BANNER'

 ┌─────────────────────────────────────────────────┐
 │  Welcome to the FactoriOS installer.            │
 │                                                 │
 │  This will wipe a disk and install FactoriOS.   │
 │  Bring up the network with `nmtui` if needed,   │
 │  then re-run `factorios-install` if it bails.   │
 └─────────────────────────────────────────────────┘

BANNER
    if ping -c1 -W2 archlinux.org >/dev/null 2>&1; then
        /usr/local/bin/factorios-install
    else
        echo "No network detected — bring it up with 'nmtui', then run:"
        echo "    factorios-install"
        echo
    fi
fi
