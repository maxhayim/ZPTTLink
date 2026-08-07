# Deploying ZPTTLink on a VPS (cloud server)

This walks through running ZPTTLink on a commodity cloud VPS instead of
physical hardware at a site. It assumes you've read the main
[README](../README.md), especially [Android Runtime
Targets](../README.md#android-runtime-targets), [Asterisk (USRP)
Backend](../README.md#asterisk-usrp-backend), and [Known
Limitations](../README.md#known-limitations). If you haven't yet, it's also
worth reading [3. Standard node + Asterisk node, connected](raspberry-pi-repeater-deployment.md#3-standard-node--asterisk-node-connected)
in the Raspberry Pi tutorial — this is that same "Asterisk node" role, just
running on a VPS instead of a second Pi.

## Why a VPS works here at all

ZPTTLink is fundamentally **a bridge for audio — TX, RX, or both** — between
Zello and whatever the radio-side target is. For the hardware backends
(AIOC/CM108/DigiRig) that target is a physical USB device, which is why those
need to run somewhere with a cable to a radio. The
[Asterisk (USRP) backend](../README.md#asterisk-usrp-backend) has no such
requirement: it's a UDP audio+PTT stream to wherever Asterisk is, and UDP
doesn't care whether "wherever" is a Pi on your desk or a data center on the
other side of the country. There's nothing left that needs to be physically
near a radio — which means the whole box can be a VPS.

This is useful when you want the reach of an Asterisk-linked node without
adding another physical Pi to a site, when your Asterisk instance is already
cloud-hosted, or when you just want the reliability of a data center's power
and network instead of whatever's available at a remote site.

## What you still need to solve

Everything about the Asterisk side is identical to the Pi tutorial's
[Asterisk node](raspberry-pi-repeater-deployment.md#2-asterisk-node) —
same USRP wire format, same ZPTTLink config, same `asterisk.host`/`port`.
The one piece that's genuinely different on a VPS is **getting Zello
running at all**, since a VPS has no display and, unlike a Pi, no Waydroid
kernel support out of the box.

```
        Zello network
              │
      ┌───────▼────────┐
      │  docker-android │   Zello audio + PTT hotkey
      │   (in a VPS)    │──────────────┐
      └────────────────┘               │
              ▲                        ▼
              │ ADB              ┌─────────────┐   UDP / USRP    ┌─────────────┐
              └──────────────────│  ZPTTLink   │───────────────▶ │  Asterisk   │
                                  │ (this repo) │◀─────────────── │  (app_rpt)  │
                                  └─────────────┘                └──────┬──────┘
                                                                         ▼
                                                       (whatever that node is linked to)
```

### Waydroid vs. docker-android on a VPS

The Pi tutorial uses Waydroid, but Waydroid needs `binder`/`ashmem` kernel
modules that most stock cloud-provider kernels don't ship — it's built for a
device you control the kernel on, not a generic cloud image. Unless your
provider explicitly documents Waydroid/LXC-container kernel support (rare),
assume it won't work and use
[docker-android](../README.md#docker-android-budtmo-or-hqarroum) instead —
it runs its own Android emulator inside the container and doesn't depend on
the host kernel having anything special, beyond ideally KVM for acceptable
performance.

**Check for KVM before picking a provider/plan:**

```bash
ls /dev/kvm && sudo apt install -y cpu-checker && kvm-ok
```

If `/dev/kvm` doesn't exist, the emulator falls back to software rendering
(`swrast`), which works but is noticeably slower — fine for a lightly-used
node, potentially not for one carrying continuous traffic. Nested
virtualization/KVM access varies a lot by provider and plan tier; confirm it
before committing to one if performance matters to you.

**Sizing:** the Android emulator inside docker-android is the heavy part,
not ZPTTLink itself. 4 vCPU / 8GB RAM is a reasonable starting point; less
and the emulator may be too slow for reliable real-time audio.

## 1. Provision the VPS

- A recent Ubuntu/Debian image, headless — no desktop environment needed.
- Confirm KVM access (above) if you care about emulator performance.
- Open only the ports you need: SSH, and whatever `asterisk.local_port` you
  settle on below if Asterisk needs to reach this box directly rather than
  over a VPN (see [Network exposure](#network-exposure) below).

## 2. System prep

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3 python3-venv python3-pip git docker.io
sudo usermod -aG docker "$USER"
# log out/in for the group change to take effect
```

## 3. Run docker-android

```bash
# budtmo/docker-android — noVNC on 6080, ADB on 5555
docker run -d --name zello-android \
  --device /dev/kvm \
  -p 6080:6080 -p 5555:5555 \
  -e EMULATOR_DEVICE="Samsung Galaxy S10" -e WEB_VNC=true \
  budtmo/docker-android
```

Drop `--device /dev/kvm` if the box doesn't have it (step 1) — the container
falls back to software rendering automatically.

Connect once, interactively, to install Zello and log in:

```bash
adb connect 127.0.0.1:5555
adb install /path/to/zello.apk
```

Open the noVNC UI at `http://<vps-ip>:6080` (put this behind an SSH tunnel —
`ssh -L 6080:localhost:6080 you@vps` — rather than leaving it open to the
internet), log into Zello, and set its PTT hotkey mode to **Toggle**, not
Hold — ZPTTLink's ADB injection is edge-triggered, same as every other
docker-android target; see [Android Runtime
Targets](../README.md#android-runtime-targets) for why.

### Audio passthrough

Per [Known Limitations](../README.md#known-limitations), docker-android
doesn't bridge audio out of the box — the images run the emulator headless
with no audio device exposed to the host. Since a VPS Asterisk node needs
that audio path to actually mean anything, this is the one piece of the VPS
tutorial that isn't optional the way it was for the docker-android section
in the README (which only needed the ADB *key* path for testing).

The general shape is routing the host's PulseAudio server over the loopback
network interface and pointing the emulator's audio backend at it — exact
flags depend on the emulator/QEMU version each image bundles, so treat this
as a starting point and check that image's own `EXTRA_FLAGS`/environment
variable docs for what it currently supports:

```bash
# on the VPS host
sudo apt install -y pulseaudio
echo "load-module module-native-protocol-tcp port=4713 auth-ip-acl=127.0.0.1" \
  | pulseaudio --start -nF /dev/stdin
```

Then point the container's emulator at `host.docker.internal:4713` (or the
Docker bridge gateway IP) via that image's audio-backend environment
variable — consult the specific `budtmo/docker-android` or
`HQarroum/docker-android` release you're running for the current variable
name, since this has changed across versions.

If you can't get this working reliably, it's not a dead end: a VPS Asterisk
node without a solved audio path is still useful for the same reason the
README calls out — testing the ADB PTT trigger path — while you sort out
the audio side, or as a place to prototype the Asterisk-facing config before
committing to it on real hardware.

## 4. Install ZPTTLink

```bash
git clone https://github.com/maxhayim/ZPTTLink.git ~/ZPTTLink
cd ~/ZPTTLink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m zpttlink --list-audio
```

If PulseAudio was just installed/started (previous step), ZPTTLink should
now see it as an audio device — that's the loopback ZPTTLink's
`audio_input_index`/`audio_output_index` will point at.

## 5. Configure ZPTTLink

Same shape as the Pi tutorial's [Asterisk
node](raspberry-pi-repeater-deployment.md#7b-asterisk-node-configure-zpttlink-for-a-network-asterisk-backend) —
nothing here is VPS-specific:

```json
{
  "radio_type": "asterisk",
  "force_serial_ptt": false,
  "disable_hotkey": false,
  "injection_mode": "adb",
  "adb_serial": "127.0.0.1:5555",

  "asterisk": {
    "host": "192.168.1.50",
    "port": 32001,
    "local_port": 0
  }
}
```

`asterisk.host` is wherever your Asterisk instance actually runs — a LAN IP
if it's on the same private network as this VPS (e.g. both behind the same
VPN), or its public/VPN IP if not. See [Network
exposure](#network-exposure) below before pointing this at a public IP
directly.

Verify:

```bash
python -m zpttlink --radio-type asterisk --asterisk-host 192.168.1.50 --asterisk-port 32001
```

## 6. Network exposure

This is the one section with no equivalent in the Pi tutorial — a box
sitting at a physical site is only reachable if someone drives there; a VPS
is reachable from the entire internet the moment a port is open.

- **Prefer a VPN between this VPS and Asterisk** — [Tailscale](https://tailscale.com/)
  or [WireGuard](https://www.wireguard.com/) — over exposing
  `asterisk.local_port` to the public internet. USRP has no authentication
  built into the protocol itself; anything that can reach the UDP port can
  send it audio and PTT.
- Keep the noVNC port (`6080`) and ADB port (`5555`) bound to localhost or
  behind an SSH tunnel, not exposed publicly — neither is meant to face the
  internet.
- A basic firewall (`ufw allow OpenSSH`, deny everything else by default,
  then allow only what step 1/this section actually needs) is worth doing
  even behind a VPN, as defense in depth.

## 7. Install as a systemd service

The same unit files from [`deploy/systemd/`](../deploy/systemd/README.md)
work here unchanged — they're generic Linux `systemd --user` units, nothing
Pi-specific about them. Swap the Waydroid-starting `zpttlink-android.service`
for one that just confirms the docker-android container is up (it's already
running as its own Docker container, started separately from step 3):

```bash
mkdir -p ~/.config/systemd/user
cp ~/ZPTTLink/deploy/systemd/zpttlink.service ~/.config/systemd/user/

sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now zpttlink.service
```

Set `docker run --restart unless-stopped` on the container itself (step 3)
so it survives a VPS reboot the same way `zpttlink.service`'s watchdog keeps
ZPTTLink itself alive.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| Emulator is unusably slow | No `/dev/kvm` — see [Waydroid vs. docker-android](#waydroid-vs-docker-android-on-a-vps); confirm your provider/plan actually offers KVM access |
| No audio reaches Zello | The PulseAudio-over-TCP wiring in [Audio passthrough](#audio-passthrough) is the most likely gap — confirm the container can actually reach port `4713` on the host, not just that PulseAudio is running |
| No `PTT DOWN (asterisk-rx)` ever appears | Confirm Asterisk is actually sending USRP traffic to this host:port and that nothing (a firewall, a NAT, a missing VPN route) is dropping UDP between the two — see [Network exposure](#network-exposure) |
| Audio relays but Zello never transmits | `force_serial_ptt`/`disable_hotkey` backwards — see [step 5](#5-configure-zpttlink); the Asterisk backend needs hotkey injection enabled |
| Zello never transmits, `PTT DOWN` logs fine | Zello's hotkey mode isn't set to **Toggle** — required for `injection_mode: adb`, see [Android Runtime Targets](../README.md#android-runtime-targets) |
| Container doesn't survive a reboot | Missing `--restart unless-stopped` on `docker run` (step 3) |
