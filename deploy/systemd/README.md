
# Systemd units for unattended Raspberry Pi deployment

These are **user** systemd units (not system units) so they run under your normal
user's session — the one with access to PipeWire/PulseAudio and, if applicable,
the Waydroid/ADB environment — without needing root or fighting `XDG_RUNTIME_DIR`
permission issues that come with running audio apps as a system service.

Full walkthrough: [`docs/raspberry-pi-repeater-deployment.md`](../../docs/raspberry-pi-repeater-deployment.md).

## Install

```bash
mkdir -p ~/.config/systemd/user
cp zpttlink.service ~/.config/systemd/user/
# Only if Zello runs inside Waydroid on this same Pi:
cp zpttlink-android.service ~/.config/systemd/user/

# Let user services start at boot without an interactive login (essential for a
# headless box):
sudo loginctl enable-linger "$USER"

systemctl --user daemon-reload
systemctl --user enable --now zpttlink.service
# If using the Waydroid companion unit:
systemctl --user enable --now zpttlink-android.service
```

## Operating

```bash
systemctl --user status zpttlink.service
journalctl --user -u zpttlink.service -f
systemctl --user restart zpttlink.service
```

## Why `Type=notify` + `WatchdogSec`

`Restart=on-failure` alone only recovers a process that actually *exits*. If the
audio thread wedges without crashing the process, a plain restart policy never
fires. ZPTTLink sends a `WATCHDOG=1` heartbeat every 10 seconds while its audio
stream is healthy; `WatchdogSec=30` gives it three missed heartbeats of slack
before systemd concludes it's hung and force-restarts it — the failure mode that
matters most for a box nobody is going to walk out to and power-cycle.
