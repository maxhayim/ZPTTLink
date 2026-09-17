# Deploying ZPTTLink on an Android phone (via Podroid)

This walks through running ZPTTLink on a spare Android phone using
[Podroid](https://github.com/ExTV/Podroid), an app that boots a real,
rootless Alpine Linux VM on the phone — no root, no emulator trick. It
assumes you've read the main [README](../README.md), especially [Works With
Any PTT App](../README.md#works-with-any-ptt-app), [Asterisk (USRP)
Backend](../README.md#asterisk-usrp-backend), and [Known
Limitations](../README.md#known-limitations).

**This is not another Android Runtime Target.** BlueStacks/Waydroid/
docker-android exist specifically to run an *Android* app (Zello) that
ZPTTLink then injects a hotkey or ADB tap into. Podroid boots *Alpine
Linux*, not Android — there's no Android userspace inside its VM at all, so
Zello (an Android-only app with no ARM64 Linux build) can't run inside it,
and there's no bridge from inside the VM back into the phone's own native
Android apps either (Podroid's guest-to-Android channel is deliberately
narrow: post a notification, forward a port, open a URL, control the VM —
not inject input into other apps). So the model here is different: treat
the phone, once Podroid is running, as **a small Linux computer** — the same
kind of box the [Raspberry Pi](raspberry-pi-repeater-deployment.md) and
[VPS](vps-deployment.md) tutorials target — and pair ZPTTLink with a
**native Linux PTT app** running inside that same VM, per [Works With Any
PTT App](../README.md#works-with-any-ptt-app), instead of an Android one.

This tutorial uses [Mumble](https://www.mumble.info/) as that PTT app —
open source, packaged for Alpine/aarch64, and a real press-to-talk hotkey
client. Swap in another Linux-native PTT app if you prefer one; nothing
below is Mumble-specific beyond the package name.

## Why this works at all

Podroid's VM is a genuine Alpine Linux 3.24 guest with its own kernel
(QEMU software emulation on any Android 8+ arm64 device, or hardware
acceleration via Android's Virtualization Framework on supported Pixels) —
real Podman/Docker/LXC, a built-in X11 viewer with audio, opt-in USB device
passthrough, and UDP-capable port forwarding. That's everything ZPTTLink
already needs on any Linux host: a package manager, an audio subsystem, and
(for the hardware backends) a USB device path.

The one thing it deliberately doesn't give you is a way to control a native
Android app from inside the guest — see above. Once you accept that and
route around it with a Linux-native PTT app instead, the rest is exactly
like running ZPTTLink anywhere else on Linux.

## What you're building

Two roles, same as the Pi and VPS tutorials — pick the one that matches
your radio side:

### 1. Standard node

A physical radio interface (AIOC/CM108/DigiRig) plugged into the phone over
USB-OTG, passed through into the guest. **Requires Podroid's QEMU backend**
— USB passthrough has no equivalent on the AVF/pKVM backend.

```
                 Alpine VM (Podroid, QEMU backend)
        ┌──────────────────────────────────────────┐
        │  Mumble (X11)   PTT hotkey    ZPTTLink    │
        │  ───────────◀──────────────── (this repo) │
        │       │ PulseAudio loopback        │       │
        │       └─────────────────────────────┘      │
        │                                    │        │
        │                          USB passthrough    │
        └────────────────────────────────────┼────────┘
                                              ▼
                                    AIOC/CM108/DigiRig
                                              │
                                        RF TX / RX
```

A human talks to this node over Mumble's own client-server network protocol
— connect a regular Mumble client, on a completely different device, to
whatever Mumble server this instance is pointed at. Nothing about that part
runs on the phone; the phone just does the automated radio↔Mumble bridging.

### 2. Asterisk node

The network (USRP) backend — no radio hardware needed on the phone at all,
so this works on **either** Podroid backend (QEMU or AVF/pKVM).

```
                 Alpine VM (Podroid, either backend)
        ┌──────────────────────────────────────────┐
        │  Mumble (X11)   PTT hotkey    ZPTTLink    │
        │  ───────────◀──────────────── (this repo) │
        │       │ PulseAudio loopback        │       │
        │       └─────────────────────────────┘      │
        └────────────────────────────────────┼────────┘
                                    UDP/USRP  │  (port-forwarded
                                              ▼   if Asterisk is elsewhere)
                                         Asterisk (app_rpt)
```

`asterisk.host` can be `127.0.0.1` if you also run Asterisk as a container
in this same guest (`podman run` — Podroid ships Podman ready to go), or a
LAN/VPN IP if Asterisk runs elsewhere. Either way, this phone becomes a
fully portable, no-root Asterisk-linked node.

## Requirements

- Any arm64 Android 8+ phone, with [Podroid](https://github.com/ExTV/Podroid)
  installed and its VM started at least once (the setup wizard sizes its
  storage — give it enough room for a Python venv, Mumble, and whatever
  else you install; 4-8GB beyond the base image is comfortable).
- **Standard node only:** a USB-OTG adapter, your AIOC/CM108/DigiRig, and
  Podroid's **QEMU backend** selected in Settings (not AVF).
- A separate device for the human operator to run their own Mumble client
  on — this phone is the automated bridge, not where a person sits and
  talks.

## 1. Enable what you need in Podroid's Settings

- **SSH** — turn it on; it's the easiest way to do the rest of this from a
  real keyboard (`ssh root@<phone-ip> -p 9922`, password `podroid` —
  change it with `passwd` once you're in).
- **USB device passthrough** (Standard node only) — enable it while the VM
  is **stopped**; it adds a USB controller at boot. QEMU backend only.
- **Port forwards** (Asterisk node only, if Asterisk runs elsewhere) — add
  a rule forwarding a host UDP port to whatever `asterisk.local_port` you
  set below. Host ports below 1024 can't be bound by an unprivileged
  Android app, so pick something like `32001` on both sides.

## 2. Install Mumble and ZPTTLink

In the Podroid terminal (or over SSH):

```sh
apk update
apk add mumble
apk add python3 py3-pip py3-numpy git gcc musl-dev python3-dev \
        portaudio-dev alsa-lib-dev linux-headers

git clone https://github.com/maxhayim/ZPTTLink.git ~/ZPTTLink
cd ~/ZPTTLink
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install pyserial pynput sounddevice loguru platformdirs pyusb
```

`--system-site-packages` picks up Alpine's `py3-numpy` instead of trying to
compile NumPy from source. Skip the GUI extras (`PySide6`) — Alpine/aarch64
doesn't reliably package Qt, and there's no need for the graphical config
editor on a headless phone-hosted box; use `config.json` + the CLI the same
way the Pi tutorial's systemd deployment does.

## 3. Launch Mumble in the built-in X11 viewer

Podroid's Xvnc server is already running on display `:0` — no display
manager, no VNC setup needed:

```sh
mumble &
```

Tap the monitor icon in the terminal's top bar to see it. Log Mumble into
whatever server you want this node to bridge, and set its **Push-to-Talk**
hotkey to match ZPTTLink's `ptt_hotkey` (default `F9`).

If you'd rather run the Mumble *server* on this same phone too, Alpine also
packages `mumble-server` — or run it as a container instead
(`podman run -d --name murmur -p 64738:64738/tcp -p 64738:64738/udp
mumble-server-image`, then a Settings → Port forwards rule for `64738`).

## 4. Wire the audio: a local PulseAudio loopback

Everything here happens *inside the guest's own PulseAudio server* — no
phone microphone or speaker is involved, since Mumble and ZPTTLink both run
in the same VM and only need to hear each other:

```sh
# a null sink ZPTTLink writes radio/Asterisk-received audio into
pactl load-module module-null-sink sink_name=zptt_to_mumble

# a null sink Mumble's own output can be captured from
pactl load-module module-null-sink sink_name=mumble_to_zptt

# loop Mumble's captured output into ZPTTLink's input side
pactl load-module module-loopback source=mumble_to_zptt.monitor sink=zptt_to_mumble
```

Then in Mumble's Audio settings, set its **output device** to
`mumble_to_zptt`, and set its **input device** (or ZPTTLink's
`audio_output_index`, depending on direction — see [How It
Works](../README.md#how-it-works)) to `zptt_to_mumble`'s monitor. Run
`python -m zpttlink --list-audio` to see these sinks' device indices for
your `config.json`. This is the same loopback-device idea as ALSA Loopback
on the Pi or BlackHole/VB-Cable on desktop — just PulseAudio modules instead
of a separate virtual-cable driver, since Podroid's guest already runs
PulseAudio for its own X11-viewer audio.

## 5. Configure ZPTTLink

**Standard node** — same shape as the Pi tutorial's [7A: physical
radio](raspberry-pi-repeater-deployment.md#7a-standard-node-configure-zpttlink-for-a-physical-radio),
pointed at the USB-passed-through device:

```json
{
  "radio_type": "auto",
  "com_port": "/dev/ttyACM0",
  "serial_wait_timeout": 30,

  "audio_input_index": 3,
  "audio_output_index": 4,

  "ptt_hotkey": "F9",
  "ptt_output": "dtr",
  "force_serial_ptt": true,
  "ignore_initial_ptt_state": true
}
```

**Asterisk node** — same shape as the Pi tutorial's [7B: Asterisk
backend](raspberry-pi-repeater-deployment.md#7b-asterisk-node-configure-zpttlink-for-a-network-asterisk-backend):

```json
{
  "radio_type": "asterisk",
  "force_serial_ptt": false,
  "disable_hotkey": false,
  "injection_mode": "auto",

  "asterisk": { "host": "127.0.0.1", "port": 32001, "local_port": 32001 },

  "audio_input_index": 3,
  "audio_output_index": 4
}
```

Either way, `injection_mode: auto`/`pynput` is what sends the PTT hotkey
into Mumble's window in the X11 viewer — this is a normal X11 session, so
host key injection works the same as it would on a desktop Linux box.

## 6. Run it at boot: an OpenRC service

Podroid's guest is Alpine, which uses **OpenRC, not systemd** — the
[`deploy/systemd/`](../deploy/systemd/README.md) unit files from the Pi
tutorial don't apply here. A minimal equivalent:

```sh
cat > /etc/init.d/zpttlink <<'EOF'
#!/sbin/openrc-run
name="zpttlink"
description="ZPTTLink Zello/radio/Asterisk bridge"
command="/root/ZPTTLink/venv/bin/python3"
command_args="-m zpttlink --config /root/ZPTTLink/config.json"
command_background=true
pidfile="/run/${RC_SVCNAME}.pid"
output_log="/var/log/zpttlink.log"
error_log="/var/log/zpttlink.log"

depend() {
    need net
}
EOF
chmod +x /etc/init.d/zpttlink
rc-update add zpttlink default
rc-service zpttlink start
```

This doesn't get the systemd watchdog (`Type=notify`/`WatchdogSec`) the Pi
tutorial's unit files have — OpenRC has no equivalent notify protocol.
`ZPTTLink`'s own `serial_wait_timeout` still helps with the boot-order race
against USB enumeration; if it starts before PulseAudio/Mumble are ready,
add a short `sleep` before `command_args` or a retry loop of your own.

## 7. Troubleshooting

| Symptom | Check |
|---|---|
| USB device never appears in the guest | Confirm USB passthrough is enabled in Settings **and** the VM was restarted after enabling it (it adds a USB controller at boot, not live) — and that you're on the QEMU backend, not AVF |
| No audio between Mumble and ZPTTLink | Re-check the `pactl load-module` chain in [step 4](#4-wire-the-audio-a-local-pulseaudio-loopback) — these modules don't persist across a VM reboot unless added to `/etc/pulse/default.pa` or re-run at startup |
| PTT hotkey doesn't reach Mumble | Confirm Mumble's window actually has focus in the X11 viewer when the hotkey fires — `pynput` injects into whatever X11 has focused, same as any desktop Linux target |
| Asterisk node: no `PTT DOWN (asterisk-rx)` ever appears | If Asterisk is outside this guest, confirm the port forward in [step 1](#1-enable-what-you-need-in-podroids-settings) is actually forwarding the right UDP port — see Podroid's own networking docs for the ≥1024 host-port rule |
| VM dies when you switch apps | Podroid's own [Limitations & troubleshooting](https://extv.github.io/Podroid/guide/limitations.html) covers this — some Android builds aggressively kill background child processes; Podroid's docs have the workaround for your device |
| Everything's slow | The QEMU backend is software-emulated (TCG) — 5-20x slower than native per Podroid's own docs. IO-bound work like ZPTTLink's audio bridging is one of the workloads that tolerates this reasonably well, but if you're on a supported Pixel, the AVF backend runs near-native (Asterisk node only — no USB passthrough on AVF) |

## A note on how confident this is

Everything in this tutorial follows directly from Podroid's own documented
behavior (its guest-to-Android bridge, USB passthrough, X11 viewer, and
PulseAudio forwarding are all as described in [Podroid's
docs](https://extv.github.io/Podroid/guide/)) and from how ZPTTLink already
works on any other Linux host. That said, this specific combination —
ZPTTLink and a Linux PTT client running together inside a Podroid VM — has
not been run end-to-end by the maintainer. Treat the PulseAudio loopback
step and the OpenRC service in particular as a starting point to verify on
your own device, not a guaranteed-working recipe.
