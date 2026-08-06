# Deploying ZPTTLink on a Raspberry Pi at a repeater site

This walks through building an unattended ZPTTLink box: a Raspberry Pi, Zello,
and a radio-side target, sealed in an enclosure and left running next to a
repeater with nobody around to babysit it. It assumes you've read the main
[README](../README.md), especially [Android Runtime
Targets](../README.md#android-runtime-targets), [Asterisk (USRP)
Backend](../README.md#asterisk-usrp-backend), and [Known
Limitations](../README.md#known-limitations).

Zello is always one side of the bridge — that part of the setup (Waydroid +
Zello) is identical either way. What differs is the *other* side, and that's
what this guide splits into two node types:

- **Standard node** — Zello bridged to a physical radio (AIOC/CM108/DigiRig)
  cabled directly to this Pi.
- **Asterisk node** — Zello bridged to a local or remote
  [Asterisk](https://www.asterisk.org/) instance over the network (USRP
  protocol), no radio hardware on this Pi at all.

You can also run *both* on the same box (two ZPTTLink processes, two configs)
if you want Zello reachable from both a local radio and an Asterisk instance —
each `radio_type` is independent per config.json.

## 1. What you're building

**Standard node:**

```
        Zello network
              │
      ┌───────▼────────┐
      │  Waydroid (or   │   Zello audio + PTT hotkey
      │  docker-android)│──────────────┐
      └────────────────┘               │
              ▲                        ▼
              │ ADB (optional)   ┌─────────────┐
              └──────────────────│  ZPTTLink   │
                                  │ (this repo) │
                                  └──────┬──────┘
                                         │ USB serial (DTR/RTS) or HID (CM108)
                                         ▼
                                  ┌─────────────┐
                                  │  AIOC/CM108 │
                                  │  interface  │
                                  └──────┬──────┘
                                         ▼
                                  Radio ↔ Repeater
```

**Asterisk node:**

```
        Zello network
              │
      ┌───────▼────────┐
      │  Waydroid (or   │   Zello audio + PTT hotkey
      │  docker-android)│──────────────┐
      └────────────────┘               │
              ▲                        ▼
              │ ADB (optional)   ┌─────────────┐
              └──────────────────│  ZPTTLink   │
                                  │ (this repo) │
                                  └──────┬──────┘
                                         │ UDP / USRP protocol
                                         ▼
                                  ┌─────────────┐
                                  │  Asterisk   │   same box (127.0.0.1)
                                  │  (app_rpt)  │   or a separate one on the LAN
                                  └──────┬──────┘
                                         ▼
                              (whatever Asterisk is linked to)
```

Everything above the divergent bottom leg runs on one Raspberry Pi either way.

## 2. Hardware

Shared, regardless of node type:

- **Raspberry Pi 4 or 5, 4GB+ RAM.** Waydroid needs a real 64-bit kernel and
  enough RAM to run an Android userspace comfortably alongside ZPTTLink's audio
  thread; don't try this on a Pi Zero/3.
- **Boot from USB SSD if the Pi model supports it**, not a microSD card. This
  is the single biggest reliability upgrade you can make for a box that will
  never get a graceful shutdown — SD cards corrupt far more easily under power
  loss than a proper SSD, and this box *will* lose power eventually.
- **A quality 5V/3A (or PD) power supply**, and ideally a small UPS (a PiJuice
  HAT or similar supercap/battery UPS) so a brief power blip doesn't corrupt
  the filesystem mid-write. At minimum, this is cheap insurance against the
  exact failure mode ("nobody's there to power-cycle it") this whole tutorial
  is trying to prevent.

**Standard node only:**

- **AIOC, CM108/CM119-based, or DigiRig USB interface** cabled to your radio.
- **A vented, weatherproof enclosure.** Sealed plastic boxes in direct sun
  turn into ovens; the Pi will thermal-throttle (or shut down) well before
  it's actually damaged, but throttling under load can still disrupt audio
  timing. Use a light-colored, ventilated (but weather-sealed against driven
  rain) enclosure, and add a heatsink/fan if it'll see summer sun.

**Asterisk node only:**

- No radio interface needed *on this Pi* — it's a network peer to Asterisk.
- Reliable connectivity to wherever Asterisk runs: if co-located (`127.0.0.1`),
  nothing extra; if remote, a stable LAN/VPN path (a flaky link here just
  means dropped audio, not a hard failure — USRP is UDP, not a persistent
  connection).
- If this Pi *also* happens to be physically at a repeater/antenna site for
  other reasons, the enclosure/thermal/RFI guidance below still applies.

### RF interference

Applies whenever this box (or its network run) is physically near a
transmitting antenna — most directly relevant to standard nodes with their own
radio cabled in, but also relevant to an Asterisk node co-located with the
Asterisk/app_rpt box that *does* have a radio attached. Real-world RFI
symptoms here look like garbled audio, a Pi that randomly reboots when the
repeater keys up, or a USB serial port that drops out under transmit.
Mitigate with:

- Ferrite chokes on the USB cable(s) and any Ethernet/power runs near the feed line
- Keeping the Pi and its PSU physically separated from the antenna feedline/duplexer, not zip-tied to it
- Proper station grounding — the Pi's enclosure and the radio should share a solid ground reference, not float independently
- Shielded USB cables over unshielded ones, especially for longer runs

## 3. Flash the OS headless

Use Raspberry Pi Imager. In the gear icon / advanced options **before
flashing**, set:

- Hostname (e.g. `zpttlink-siteA`)
- Enable SSH, **key-based auth** (skip password auth entirely if you can — this
  box has no keyboard to type a password recovery on anyway)
- WiFi SSID/password (prefer Ethernet if the site has it — it's far more
  reliable than WiFi for something you can't walk over and reset)
- Locale/timezone, so your logs have sane timestamps

Boot it, then `ssh pi@zpttlink-siteA.local` (mDNS/avahi is enabled by default
on Raspberry Pi OS).

## 4. System prep

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3 python3-venv python3-pip git \
  libasound2-dev build-essential

# Serial + audio group access for the 'pi' user (or whatever user you're using)
sudo usermod -aG dialout,audio,plugdev "$USER"
# Log out/in (or reboot) for the group change to take effect
```

## 5. Install Waydroid and Zello

This step is the same for both node types — Zello's side of the bridge never
changes.

```bash
curl https://repo.waydro.id | sudo bash
sudo apt install -y waydroid
sudo waydroid init
```

Start a session and get Zello installed once, interactively, over VNC (enable
it via `sudo raspi-config` → Interface Options → VNC, then connect with any VNC
client) — this is the easiest way to see Waydroid's screen the first time:

```bash
waydroid session start
```

Sideload the Zello APK (`adb install /path/to/zello.apk`, after `adb connect
127.0.0.1:5555` — Waydroid exposes ADB once enabled, see Waydroid's own docs
for `adb_enabled`), log into your Zello account, and set Zello's PTT hotkey to
match your ZPTTLink config (default `F9`). Do this once with a display attached
or over VNC; you won't need a display again after this.

## 6. Install ZPTTLink

```bash
git clone https://github.com/maxhayim/ZPTTLink.git ~/ZPTTLink
cd ~/ZPTTLink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

```bash
python -m zpttlink --list-audio
```

If that comes back empty, see the [PipeWire/ALSA
troubleshooting](../README.md#linux-notes) note in the README before going
further — this is a common Pi-specific failure mode and there's a documented
fix path for it.

The rest of the configuration diverges by node type — pick your section below.

## 7A. Standard node: configure ZPTTLink for a physical radio

```bash
python -m zpttlink --list-serial
```

Write `~/ZPTTLink/config.json` (or run the GUI once over VNC/X-forwarding
with `python -m zpttlink --gui` and hit Save Config — same result):

```json
{
  "radio_type": "auto",
  "com_port": "/dev/ttyACM0",
  "serial_wait_timeout": 30,

  "audio_input_index": 1,
  "audio_output_index": 2,

  "ptt_hotkey": "F9",
  "ptt_output": "dtr",
  "force_serial_ptt": true,
  "ignore_initial_ptt_state": true,

  "vox": { "enabled": true, "threshold": 0.01 }
}
```

`force_serial_ptt: true` means ZPTTLink keys the radio directly via DTR/RTS —
deterministic, and it doesn't depend on Zello's hotkey reaching Waydroid at
all. If you'd rather also trigger Zello's own hotkey so its UI reflects TX
state, set `force_serial_ptt: false` and either `injection_mode: adb` (see
[Android Runtime Targets](../README.md#android-runtime-targets) — remember
Zello's hotkey mode needs to be **Toggle**, not Hold, for ADB) or leave it on
`auto` for host key injection.

Confirm hardware PTT works before wiring in Zello at all:

```bash
python -m zpttlink --test-ptt --serial /dev/ttyACM0
```

**Optional: RX audio (radio → Zello).** Off by default. If you have a
*separate* RX radio/receiver (standard repeater-controller topology — see
[RX Audio](../README.md#rx-audio-hardware-backends) in the README for why a
single transceiver is a bad fit here), add:

```json
{
  "rx_audio_input_index": 3,
  "rx_audio_output_index": 4,
  "rx_vox": { "enabled": true, "threshold": 0.01 }
}
```

Skip to [step 8](#8-install-as-a-systemd-user-service) once this is working.

## 7B. Asterisk node: configure ZPTTLink for a network Asterisk backend

No radio interface to find — point ZPTTLink at Asterisk instead. If Asterisk
runs on this same Pi, use `127.0.0.1`; if it's elsewhere on your network, use
that host's address.

```json
{
  "radio_type": "asterisk",
  "force_serial_ptt": false,
  "disable_hotkey": false,
  "injection_mode": "auto",

  "asterisk": {
    "host": "127.0.0.1",
    "port": 32001,
    "local_port": 0
  },

  "audio_input_index": 1,
  "audio_output_index": 2
}
```

**This is the one config where `force_serial_ptt: false` +
`disable_hotkey: false` are required, not optional** — there's no hardware
line for this backend to key, so hotkey injection is the only way audio
arriving from Asterisk actually gets relayed into Zello's network. ZPTTLink
logs a warning at startup if you get this backwards. See [Asterisk (USRP)
Backend](../README.md#asterisk-usrp-backend) in the README for how audio
flows in this mode (it's genuinely full duplex, unlike the standard-node
TX path).

Confirm connectivity and audio before relying on it:

```bash
python -m zpttlink --radio-type asterisk --asterisk-host 127.0.0.1 --asterisk-port 32001
```

Watch the log for `Asterisk USRP backend: sending to ...` and, once Asterisk
is actually sending audio your way, `PTT DOWN (asterisk-rx)`.

## 8. Install as a systemd user service

Ready-made unit files are in [`deploy/systemd/`](../deploy/systemd/README.md).
The service just runs `python -m zpttlink --config config.json` — since your
node type lives entirely in `config.json`, the unit file itself is identical
for both node types.

```bash
mkdir -p ~/.config/systemd/user
cp ~/ZPTTLink/deploy/systemd/zpttlink.service ~/.config/systemd/user/
cp ~/ZPTTLink/deploy/systemd/zpttlink-android.service ~/.config/systemd/user/

sudo loginctl enable-linger "$USER"   # start user services at boot, no login needed
systemctl --user daemon-reload
systemctl --user enable --now zpttlink-android.service
systemctl --user enable --now zpttlink.service
```

Watch it come up:

```bash
journalctl --user -u zpttlink.service -f
```

Standard node: you should see the serial/CM108 device get picked up, the
audio stream start, and `PTT system ready`. Key the radio (or make some noise
into the mic, if VOX is enabled) and confirm you see `PTT DOWN` / `PTT UP`
and the radio actually transmits.

Asterisk node: you should see the USRP backend connect, `PTT system ready`,
and — once there's traffic on the Asterisk side — `PTT DOWN (asterisk-rx)`.

Either way, reboot the whole Pi once here (`sudo reboot`) and confirm
everything comes back up on its own — that's the real test, not just
`systemctl start`.

## 9. Unattended hardening

- **Power loss:** if you skipped the UPS, at minimum use a filesystem that
  tolerates unclean shutdowns reasonably (ext4's default journaling helps, but
  isn't a substitute for real power protection). A USB SSD boot drive (step 2)
  matters more here than almost anything else on this list.
- **SD/SSD wear:** ZPTTLink's own logging is modest (512KB × 2 rotated files),
  but combined with normal OS logging over months of 24/7 runtime, consider
  `journalctl`'s own rotation limits (`SystemMaxUse=` in
  `/etc/systemd/journald.conf`) so logs don't grow unbounded.
- **Network:** prefer wired Ethernet. If you're on WiFi/cellular at a remote
  site, consider a simple watchdog cron job that reboots the Pi if it can't
  reach the internet for N minutes — a box that silently drops off the network
  and never recovers is just as bad as one that crashes. This matters even
  more for an Asterisk node, since the whole radio-side leg is the network.
- **Remote access without port-forwarding:** most repeater sites aren't going
  to give you a public IP to port-forward into. Consider
  [Tailscale](https://tailscale.com/) or ZeroTier so you can `ssh` in from
  anywhere without exposing the box directly to the internet.
- **Updates:** weigh `unattended-upgrades` (security patches, unattended)
  against the risk of an update landing badly on a box nobody can walk over to
  fix. A common middle ground: apply updates manually during a scheduled
  maintenance visit, not automatically.
- **The systemd watchdog is your friend here.** `zpttlink.service` uses
  `Type=notify` + `WatchdogSec=30` — if the audio thread wedges (not crashes,
  *wedges*) without you there, systemd notices the missing heartbeat and
  restarts it on its own. See [`deploy/systemd/README.md`](../deploy/systemd/README.md)
  for why this matters more than a plain restart policy.

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| `--list-audio` empty | See [Linux Notes](../README.md#linux-notes) — usually a missing PipeWire/Pulse compatibility layer |
| **Standard node:** radio keys immediately on start | Confirm `ignore_initial_ptt_state: true`; check `journalctl` for "Ignoring initial PTT state" on startup |
| **Standard node:** service won't come up after reboot | `journalctl --user -u zpttlink.service -b` — likely the USB device enumerated later than `serial_wait_timeout`; raise it in config.json (and `TimeoutStartSec` in the unit if you raise it a lot) |
| **Standard node:** RX audio cuts out right as it starts relaying | You likely have RX wired to the same radio the backend keys for TX — see the wiring note in [RX Audio](../README.md#rx-audio-hardware-backends); use `ptt_output: "none"` for single-radio RX |
| **Asterisk node:** no `PTT DOWN (asterisk-rx)` ever appears | Confirm Asterisk is actually sending USRP traffic to this host:port, and that nothing (a firewall, a NAT) is dropping UDP between the two |
| **Asterisk node:** audio relays but Zello never transmits | You have `hotkey_enabled` off (`force_serial_ptt: true` or `--no-hotkey`) — the Asterisk backend needs hotkey injection to relay into Zello; see [step 7B](#7b-asterisk-node-configure-zpttlink-for-a-network-asterisk-backend) |
| Zello never transmits, but `PTT DOWN` logs fine | You're likely on `injection_mode: adb` without Zello's hotkey set to **Toggle** — see [Android Runtime Targets](../README.md#android-runtime-targets) |
| Random reboots when the repeater keys up | RFI — see the hardware section above; try ferrite chokes and re-check grounding before suspecting the Pi itself |
