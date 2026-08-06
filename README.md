<p align="center">
  <img src="assets/logo.png" alt="ZPTTLink Logo" width="200"/>
</p>

<p align="center">
  <strong>An open-source, all-in-one linking bridge</strong>
</p>

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.8%2B-blue" alt="Python Version">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  </a>
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platform">
</p>

<h1>ZPTTLink</h1>

<p>ZPTTLink is an open-source, all-in-one linking bridge. Deterministic DTR/RTS/CM108 hardware PTT or a network Asterisk (USRP) backend, with pynput/ydotool/ADB key injection for BlueStacks, Waydroid, and docker-android.</p>

<p>Compatible radio interfaces include the <a href="https://github.com/skuep/AIOC">AIOC (All-In-One Cable)</a>, CM108/CM119-based USB sound fobs, DigiRig, and other USB serial/audio radio cables — see <a href="#requirements">Requirements</a>. Both the radio side and the Zello side are configurable independently: pick a hardware backend or <a href="#asterisk-usrp-backend">Asterisk (USRP)</a> for the radio side, and BlueStacks/Waydroid/docker-android for where Zello runs — see <a href="#android-runtime-targets">Android Runtime Targets</a>.</p>

<p>This tool is ideal for GMRS and ham radio operators, emergency communications volunteers, and hobbyists who want to build a software-based radio gateway.</p>

<h2>Signal Flow Overview</h2>

<pre>
          ┌──────────────┐
          │     Zello    │
          │ (BlueStacks /│
          │   Waydroid)  │
          └──────┬───────┘
                 │
        TX Audio  │  RX Audio
                 │
          ┌──────▼───────┐
          │   ZPTTLink   │
          │  (PC / Host) │
          │              │
          │  • Audio I/O │
          │  • PTT Ctrl  │
          └──────┬───────┘
                 │
        USB Audio │  USB PTT
                 │
          ┌──────▼───────┐
          │     AIOC     │
          │  (or equiv.) │
          └──────┬───────┘
                 │
           RF TX / RX
                 │
          ┌──────▼───────┐
          │     Radio    │
          └──────────────┘
</pre>

<h2>Features</h2>

<ul>
  <li>Compatible with AIOC, CM108/CM119-based, DigiRig, and other USB serial/audio radio cables</li>
  <li>Detects PTT signals via USB serial (DigiRig DTR/RTS) or USB HID GPIO (CM108/CM119)</li>
  <li><strong>Multiple ways to trigger PTT in the Zello target, selectable via <code>injection_mode</code>:</strong>
    <ul>
      <li><code>pynput</code> — standard host keyboard injection (X11 / macOS / Windows)</li>
      <li><code>ydotool</code> — Linux <code>/dev/uinput</code> injection; used automatically on a detected Wayland session, where host key injection is normally blocked</li>
      <li><code>adb</code> — sends <code>input keyevent</code> directly into an Android target over ADB; the mechanism for <a href="#android-runtime-targets">docker-android targets</a>, since they have no host window to inject into at all</li>
      <li><code>auto</code> (default) — picks pynput or ydotool automatically based on the detected session</li>
    </ul>
  </li>
  <li>Direct hardware PTT via serial DTR/RTS or CM108 GPIO, independent of key injection entirely — the most reliable option when the radio, not the app, is the thing you need to key</li>
  <li><strong>Full duplex audio</strong>: Zello → radio (TX) plus an optional, independent radio → Zello (<a href="#rx-audio-hardware-backends">RX</a>) path for the hardware backends, and always-duplex for the <a href="#asterisk-usrp-backend">Asterisk (USRP) backend</a>, since USRP is bidirectional by design</li>
  <li>Cross-platform support for Windows, macOS, and Linux (including Raspberry Pi)</li>
  <li><strong>Two operating modes:</strong>
    <ul>
      <li>Terminal (CLI) mode for lightweight deployments and automation</li>
      <li>Graphical user interface (GUI) for easy configuration and monitoring</li>
    </ul>
  </li>
  <li>Built-in GUI features include:
    <ul>
      <li>Serial device auto-refresh</li>
      <li>Audio device selector</li>
      <li>PTT indicator light</li>
      <li>Radio-style push-to-talk button</li>
      <li>Runtime start/stop controls</li>
      <li>Config editor with save button</li>
      <li>Android target / injection mode selector, with an ADB serial field for docker-android targets</li>
      <li>RX audio device selectors and VOX threshold, with a one-click enable/disable toggle</li>
    </ul>
  </li>
  <li>Audio routing via <a href="https://vb-audio.com/Cable/">VB-Cable (Windows)</a>, <a href="https://existential.audio/blackhole/">BlackHole (macOS)</a>, or <a href="https://www.alsa-project.org/wiki/Loopback_Device">ALSA Loopback (Linux)</a></li>
</ul>

<h2>Requirements</h2>

<ul>
  <li>AIOC, CM108/CM119, or compatible USB PTT/audio interface</li>
  <li>Python 3.8 or newer</li>
  <li>Zello installed inside <a href="https://www.bluestacks.com/">BlueStacks</a>, <a href="https://waydro.id/">Waydroid</a>, or a <a href="#android-runtime-targets">docker-android</a> container</li>
  <li><strong>For <code>injection_mode: adb</code> only:</strong> <a href="https://developer.android.com/tools/adb">Android platform-tools</a> (<code>adb</code>) on the host</li>
  <li><strong>For Wayland hosts only:</strong> <a href="https://github.com/ReimuNotMoe/ydotool">ydotool</a> + a running <code>ydotoold</code>, used automatically as the key-injection fallback</li>
</ul>

<h3>Python Dependencies</h3>

<p>Install all dependencies with:</p>

<pre><code>pip install -r requirements.txt
</code></pre>

<ul>
  <li><strong>Core:</strong> pyserial, pynput, sounddevice, numpy, loguru, platformdirs, pyusb, PySide6</li>
  <li><strong>Windows:</strong> pycaw</li>
  <li><strong>macOS:</strong> pyobjc</li>
  <li><strong>Linux:</strong> pulsectl</li>
</ul>

<h3>Linux Notes</h3>

<ul>
  <li>ZPTTLink works with both <a href="https://www.alsa-project.org/wiki/Main_Page">ALSA</a> and <a href="https://www.freedesktop.org/wiki/Software/PulseAudio/">PulseAudio</a>.</li>
  <li>If your system uses <a href="https://pipewire.org/">PipeWire</a>, make sure the <strong>PulseAudio compatibility layer</strong> is enabled so <code>pulsectl</code> can function correctly.</li>
  <li>ALSA Loopback must be enabled for audio routing. See: <a href="https://www.alsa-project.org/wiki/Loopback_Device">ALSA Loopback Device</a>.</li>
</ul>


<h2>Installation and Setup</h2>

<p><strong>Deploying to an unattended Raspberry Pi</strong> (e.g. boxed up at a remote site)? See the dedicated <a href="docs/raspberry-pi-repeater-deployment.md">Raspberry Pi deployment tutorial</a> — hardware, headless OS setup, Waydroid + Zello, systemd autostart with a watchdog, and outdoor/unattended hardening. The steps below are the general/manual install; the Pi tutorial builds on them.</p>

<ol>
  <li>Install Python:
    <ul>
      <li><a href="https://www.python.org/downloads/windows">Windows</a></li>
      <li>macOS: Use Homebrew:
        <pre><code>brew install python</code></pre>
      </li>
      <li>Linux: Use your package manager (example for Debian/Ubuntu):
        <pre><code>sudo apt install python3 python3-venv</code></pre>
      </li>
    </ul>
  </li>

  <li>Install virtual audio driver (choose your OS above).</li>

  <li>Clone the repository:
    <pre><code>git clone https://github.com/maxhayim/ZPTTLink.git
cd ZPTTLink</code></pre>
  </li>

  <li>Create and activate a virtual environment:
    <ul>
      <li>Windows:
        <pre><code>python -m venv venv
venv\Scripts\activate</code></pre>
      </li>
      <li>macOS/Linux:
        <pre><code>python3 -m venv venv
source venv/bin/activate</code></pre>
      </li>
    </ul>
  </li>

  <li>Install dependencies:
    <pre><code>pip install -r requirements.txt</code></pre>
  </li>
</ol>

<h2>Usage</h2>

<h3>Terminal (CLI) Mode</h3>

<ol>
  <li>Activate your virtual environment:
    <pre><code>source venv/bin/activate</code></pre>
  </li>

  <li>Run ZPTTLink in terminal mode:
    <pre><code>python -m zpttlink</code></pre>
  </li>

  <li>Available commands:
    <ul>
      <li><code>help</code> — Displays available commands and usage info</li>
      <li><code>q</code> or <code>quit</code> — Safely exits the program</li>
    </ul>
  </li>
</ol>

<h3>Graphical Interface (GUI)</h3>

<p>ZPTTLink also includes a cross-platform graphical interface.</p>

<pre><code>python -m zpttlink --gui</code></pre>

<p>The GUI provides:</p>

<ul>
  <li>Automatic detection of serial devices</li>
  <li>Audio input/output device selection</li>
  <li>PTT status indicator (Idle / RX / TX)</li>
  <li>Large radio-style PTT button</li>
  <li>Start/Stop runtime control</li>
  <li>Configuration editor with save functionality</li>
</ul>

<p>The GUI works on:</p>

<ul>
  <li>Windows</li>
  <li>macOS</li>
  <li>Linux</li>
  <li>Raspberry Pi</li>
</ul>

<h2>Android Runtime Targets</h2>

<p>Zello can run in four different places relative to ZPTTLink. Which one you're using determines how PTT actually reaches it — set <code>injection_mode</code> (and <code>adb_serial</code>, if applicable) accordingly.</p>

<h3>BlueStacks (macOS)</h3>

<ul>
  <li><code>injection_mode: pynput</code> (default on macOS)</li>
  <li>Install BlueStacks, install Zello inside it, and set Zello's PTT hotkey to match <code>ptt_hotkey</code> in your config (default <code>F9</code>)</li>
  <li>Route audio through <a href="https://existential.audio/blackhole/">BlackHole</a>: BlueStacks' input device set to the BlackHole loopback, ZPTTLink's <code>audio_output_index</code> pointed at the same BlackHole device</li>
  <li>macOS requires granting Accessibility permission to the terminal/app running ZPTTLink for pynput key injection to work at all (System Settings → Privacy & Security → Accessibility)</li>
</ul>

<h3>Waydroid (Linux)</h3>

<ul>
  <li>On an X11 session: <code>injection_mode: pynput</code> works the same as BlueStacks</li>
  <li>On a Wayland session (common on modern distros): <code>injection_mode: auto</code> switches to <code>ydotool</code> automatically — install <code>ydotool</code> and run <code>ydotoold</code> as a service first</li>
  <li><strong>Known limitation:</strong> Waydroid runs Android inside its own container with its own input stack. Even when <code>ydotool</code> successfully injects a key on the host, Waydroid does not reliably forward that synthetic event into the Android session — this is a Waydroid input-isolation limitation, not something ZPTTLink controls. If key injection doesn't reach Zello inside Waydroid, ADB is usually more reliable (Waydroid exposes an ADB target once <code>waydroid shell settings put global adb_enabled 1</code> or equivalent is configured — see Waydroid's own docs) — set <code>injection_mode: adb</code> and point <code>adb_serial</code> at it, same as the docker-android targets below</li>
  <li>Route audio through <a href="https://www.alsa-project.org/wiki/Loopback_Device">ALSA Loopback</a> or PulseAudio's <code>module-loopback</code>, since Waydroid can be configured to use the host's PulseAudio/PipeWire server directly</li>
</ul>

<h3>docker-android (budtmo or HQarroum)</h3>

<p>Both <a href="https://github.com/budtmo/docker-android">budtmo/docker-android</a> and <a href="https://github.com/HQarroum/docker-android">HQarroum/docker-android</a> run a real Android <strong>emulator</strong> inside a container, controlled over ADB (budtmo also adds a noVNC web UI). ZPTTLink talks to Zello inside either one the same way: over ADB.</p>

<pre><code># budtmo/docker-android — noVNC on 6080, ADB on 5555
docker run -d -p 6080:6080 -p 5555:5555 \
  -e EMULATOR_DEVICE="Samsung Galaxy S10" -e WEB_VNC=true \
  budtmo/docker-android

# HQarroum/docker-android — ADB on 5555
docker run -d -p 5555:5555 hqarroum/docker-android
</code></pre>

<ol>
  <li>Connect and install Zello inside the emulator (once, per container):
    <pre><code>adb connect 127.0.0.1:5555
adb install /path/to/zello.apk</code></pre>
  </li>
  <li>Open Zello inside the emulator (via budtmo's noVNC at <code>http://localhost:6080</code>, or <code>scrcpy</code> against the ADB target) and set Zello's PTT hotkey mode to <strong>Toggle</strong>, not Hold — see below for why.</li>
  <li>Configure ZPTTLink:
    <pre><code>{
  "injection_mode": "adb",
  "adb_serial": "127.0.0.1:5555",
  "ptt_hotkey": "F9"
}</code></pre>
    or via the CLI: <code>python -m zpttlink --injection-mode adb --adb-serial 127.0.0.1:5555</code>, or in the GUI's "Android Target" panel.
  </li>
</ol>

<p><strong>Why Toggle, not Hold:</strong> Android's <code>adb shell input keyevent</code> dispatches a key press and release together as a single, instantaneous event — there is no way to hold a key down over ADB the way a real keyboard (or DTR/RTS) can. ZPTTLink's ADB mode sends one tap when the radio's PTT goes down, and deliberately does nothing when it goes back up. This matches Zello's <strong>Toggle</strong> hotkey mode (tap once to start transmitting, tap again to stop) but will not work correctly with Zello's <strong>Hold</strong> mode, since there's no way to release a key ZPTTLink never truly held.</p>

<p><strong>Audio is not bridged for either docker-android project.</strong> Both run headless by default — HQarroum's image explicitly starts the emulator with <code>-no-audio</code>, and budtmo's does not document any audio passthrough at all. That means ZPTTLink's audio bridge (mic-in → radio-out) has nothing to connect to inside a stock container: there is no virtual sound device reachable from the host. Getting audio into the emulator requires routing PulseAudio over the network into the container yourself — for example, enabling <code>module-native-protocol-tcp</code> on the host's PulseAudio server and pointing the emulator's own <code>-audio-backend</code>/<code>EXTRA_FLAGS</code> at it (see each project's <code>EXTRA_FLAGS</code> environment variable). Exact flags depend on the emulator/QEMU version bundled in the image, so treat this as a starting point, not a copy-paste recipe — consult the specific image's own issues/docs for the audio flags it currently supports. Until that's wired up, these two targets are useful for <strong>testing the ADB PTT trigger path</strong> with Zello's Toggle mode, not for a working end-to-end audio bridge.</p>

<h2>Asterisk (USRP) Backend</h2>

<p>Set <code>radio_type: "asterisk"</code> and ZPTTLink connects to a local or remote <a href="https://www.asterisk.org/">Asterisk</a> instance over the network instead of a physical radio interface — using the <strong>USRP protocol</strong>, the UDP audio+PTT wire format Asterisk's <code>app_rpt</code> module (<code>chan_usrp</code>) uses to let an external program act as a "radio" node without being a compiled Asterisk channel driver. No AIOC/CM108/DigiRig hardware is needed for this backend at all.</p>

<p>This is <strong>additive, not a replacement</strong> — the existing hardware backends are unchanged. ZPTTLink now supports two independent kinds of "radio side": physical hardware, or Asterisk over the network. Pick whichever matches your setup with <code>--radio-type</code>.</p>

<p>It runs equally well <strong>co-located on the same Pi/computer as Asterisk</strong> (point it at <code>127.0.0.1</code>) or <strong>on a separate box</strong> talking to a remote Asterisk instance over LAN/VPN — both are the exact same code path, just a different <code>asterisk.host</code>.</p>

<h3>Configuration</h3>

<pre><code>{
  "radio_type": "asterisk",
  "force_serial_ptt": false,
  "disable_hotkey": false,
  "injection_mode": "auto",

  "asterisk": {
    "host": "127.0.0.1",
    "port": 32001,
    "local_port": 0
  }
}</code></pre>

<p>Or via the CLI: <code>python -m zpttlink --radio-type asterisk --asterisk-host 127.0.0.1 --asterisk-port 32001</code>. In the GUI, pick "asterisk" from the <strong>Radio Backend</strong> dropdown in the Connection panel.</p>

<p><strong>Important:</strong> unlike the hardware backends (which default to <code>force_serial_ptt: true</code>, disabling hotkey injection since a serial/GPIO line keys the radio directly), the Asterisk backend has no hardware to key — it <em>needs</em> hotkey injection enabled with a working <code>injection_mode</code> so that audio arriving from Asterisk actually gets relayed into Zello's network. Leaving <code>force_serial_ptt: true</code> with <code>radio_type: asterisk</code> logs a warning at startup and effectively means Asterisk-side audio reaches Zello's mic input but Zello never transmits it.</p>

<h3>How audio flows</h3>

<p>This is the one backend where full duplex is real:</p>

<ul>
  <li><strong>Zello → Asterisk:</strong> Zello's outgoing audio (<code>audio_input_index</code>) is resampled to 8kHz/16-bit mono and sent as USRP voice frames. A local VOX gate decides the outbound <code>keyup</code> flag frame-by-frame.</li>
  <li><strong>Asterisk → Zello:</strong> incoming USRP voice frames are resampled up to the device rate and written into <code>audio_output_index</code> (point this at whatever virtual audio device feeds Zello's <em>microphone</em> input — the reverse role <code>audio_output_index</code> plays for the hardware backends, where it feeds the radio's TX audio input instead). The incoming frame's <code>keyup</code> field drives <code>ptt.down()</code>/<code>ptt.up()</code>, which is what triggers the hotkey injection that makes Zello actually transmit the relayed audio.</li>
</ul>

<h2>RX Audio (Hardware Backends)</h2>

<p>The DigiRig/CM108/Signalink backends now support a second, independent audio path: the radio's <em>received</em> audio relayed back into Zello. This is off by default (matching earlier versions) — set both <code>rx_audio_input_index</code> and <code>rx_audio_output_index</code> to enable it, or use the GUI's <strong>Enable RX (radio → Zello)</strong> checkbox in the Audio panel.</p>

<pre><code>{
  "rx_audio_input_index": 3,
  "rx_audio_output_index": 4,
  "rx_vox": {
    "enabled": true,
    "threshold": 0.01,
    "attack_ms": 20,
    "release_ms": 150,
    "hang_ms": 200
  },
  "audio": {
    "rx_gain": 0.5
  }
}</code></pre>

<p>This runs as a second, independent audio stream alongside the existing TX one: <code>rx_audio_input_index</code> captures the radio's received audio, an RX-side VOX gate (separately tunable from the TX <code>vox</code> block — receive-audio levels are rarely close to Zello's loopback level) decides when there's real traffic, and while active the audio is written into <code>rx_audio_output_index</code> (point this at whatever virtual device feeds Zello's <em>microphone</em> input) while <code>ptt.down()</code>/<code>ptt.up()</code> fires so hotkey injection actually relays it into Zello's network — not just silently played into its mic input.</p>

<p><strong>Important wiring note:</strong> triggering RX also calls the configured backend's <code>ptt_on()</code>/<code>ptt_off()</code> — the same call TX-side VOX uses to key the radio. That's correct and intentional for a proper repeater topology with <strong>separate RX and TX radios</strong> (RX radio's audio feeds <code>rx_audio_input_index</code>; the backend's DTR/RTS/GPIO line keys the separate TX radio). It is very likely <strong>wrong</strong> for a single-transceiver setup, where keying the same radio's PTT while its own RX audio is mid-relay will cut off the very audio you're trying to relay (most transceivers mute RX while transmitting). If you only have one radio, either leave RX disabled, or set <code>ptt_output: "none"</code> so the backend's PTT line is never asserted and RX only drives hotkey injection into Zello.</p>

<h2>How It Works</h2>

<p>ZPTTLink listens for a PTT signal from your radio interface — either a serial control line (DigiRig DTR/RTS) or a USB HID GPIO line (CM108/CM119). When it fires, ZPTTLink does two things in parallel:</p>

<ol>
  <li><strong>Triggers Zello's PTT</strong>, using whichever <code>injection_mode</code> the target needs: a simulated keypress (pynput on X11/macOS/Windows, ydotool on Wayland), or an ADB <code>input keyevent</code> tap for a docker-android/ADB-reachable target. See <a href="#android-runtime-targets">Android Runtime Targets</a> for which one applies to your setup.</li>
  <li><strong>Keys the radio directly</strong> via serial DTR/RTS or CM108 GPIO, independent of whether the key injection actually reached Zello — this is the deterministic path the project name refers to.</li>
</ol>

<p>Microphone/Zello audio is routed to the radio's audio output via a virtual audio driver, creating the Zello-to-RF link. If <a href="#rx-audio-hardware-backends">RX audio</a> is configured, the reverse leg (radio's received audio → Zello) runs as a second, independent stream, closing the loop into a full duplex bridge.</p>

<p>The <a href="#asterisk-usrp-backend">Asterisk (USRP) backend</a> works differently from all of the above — audio flows over the network rather than to/from local devices; see that section for how it actually works in that mode.</p>

<h2>Known Limitations</h2>

<ul>
  <li><strong>Hardware-backend RX assumes a separate RX radio if PTT output is enabled.</strong> See the wiring note in <a href="#rx-audio-hardware-backends">RX Audio</a> — on a single transceiver, keying its own PTT during RX relay will cut off the audio being relayed. Use <code>ptt_output: "none"</code> for single-radio RX.</li>
  <li><strong>ADB PTT is edge-triggered, not press-and-hold.</strong> See <a href="#android-runtime-targets">Android Runtime Targets</a> — it requires Zello's hotkey mode set to Toggle, not Hold.</li>
  <li><strong>No audio bridge into docker-android by default.</strong> Both supported docker-android images run headless with no audio passthrough out of the box; wiring that up is a manual PulseAudio-over-network step outside ZPTTLink's control.</li>
  <li><strong>Waydroid input isolation.</strong> Synthetic key events (ydotool or otherwise) injected on the host are not guaranteed to reach an app running inside Waydroid's container; ADB is the more reliable fallback there too.</li>
</ul>

<h2>License</h2>


This project is licensed under the MIT License.

See the [LICENSE](LICENSE) file for details.  
Full license text: https://opensource.org/licenses/MIT

<h2>Contributing</h2>

<p>Pull requests are welcome. Open an issue first to discuss ideas or report bugs.</p>

<h2>Related Projects</h2>

<ul>
  <li><a href="https://www.asterisk.org/">Asterisk</a></li>
  <li><a href="https://github.com/skuep/AIOC">AIOC – All-In-One Cable</a></li>
  <li><a href="https://github.com/ExistentialAudio/BlackHole">BlackHole (macOS)</a></li>
  <li><a href="https://github.com/alsa-project/alsa-utils">ALSA Utils / Loopback (Linux)</a></li>
  <li><a href="https://github.com/bluestacks">BlueStacks</a></li>
  <li><a href="https://github.com/waydroid">Waydroid</a></li>
  <li><a href="https://github.com/budtmo/docker-android">budtmo/docker-android</a></li>
  <li><a href="https://github.com/HQarroum/docker-android">HQarroum/docker-android</a></li>
  <li><a href="https://github.com/ReimuNotMoe/ydotool">ydotool</a></li>
  <li><a href="https://github.com/vb-audio-software">VB-Audio (VB-Cable)</a></li>
</ul>

<h2>Acknowledgments</h2>

<p>Portions of this project are based on or inspired by the <a href="https://github.com/skuep/AIOC">AIOC (All-in-one-Cable)</a>.<br>  
Zello® for Android is a trademark of Zello Inc., Android™ is a trademark of Google LLC, and both are used here solely for interoperability purposes.  
All other trademarks are the property of their respective owners.</p>

