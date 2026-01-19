<p align="center">
  <img src="assets/logo.png" alt="ZPTTLink Logo" width="200"/>
</p>

<p align="center">
  <strong>A full Zello ↔ radio gateway with deterministic PTT control</strong>
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

<p>ZPTTLink is an open-source, cross-platform application that bridges Zello (running inside <a href="https://www.bluestacks.com/">BlueStacks</a> or <a href="https://waydro.id/">Waydroid</a>) with radio gateway hardware like the <a href="https://github.com/skuep/AIOC">AIOC (All-In-One Cable)</a>. It enables seamless Push-to-Talk (PTT) control and audio routing, allowing users to link RF radios to Zello using only a computer.</p>

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
  <li>Compatible with AIOC, CM108-based, and other USB serial/audio radio cables</li>
  <li>Detects PTT signals via USB serial</li>
  <li>Simulates keypresses or mouse events to trigger Zello’s Push-to-Talk</li>
  <li>Cross-platform support for Windows, macOS, and Linux</li>
  <li>Minimal and simple (KISS — no GUI required)</li>
  <li>Audio routing via <a href="https://vb-audio.com/Cable/">VB-Cable (Windows)</a>, <a href="https://existential.audio/blackhole/">BlackHole (macOS)</a>, or <a href="https://www.alsa-project.org/wiki/Loopback_Device">ALSA Loopback (Linux)</a></li>
</ul>

<h2>Requirements</h2>

<ul>
  <li>AIOC or compatible USB PTT/audio interface</li>
  <li>Python 3.8 or newer</li>
  <li>Zello installed inside <a href="https://www.bluestacks.com/">BlueStacks</a> or <a href="https://waydro.id/">Waydroid</a></li>
</ul>

<h3>Python Dependencies</h3>

<p>Install all dependencies with:</p>

<pre><code>pip install -r requirements.txt
</code></pre>

<ul>
  <li><strong>Core:</strong> pyserial, pynput, sounddevice, numpy, loguru, platformdirs</li>
  <li><strong>Windows:</strong> pycaw</li>
  <li><strong>macOS:</strong> pyobjc</li>
  <li><strong>Linux:</strong> pulsectl, pyalsa</li>
</ul>

<h3>Linux Notes</h3>

<ul>
  <li>ZPTTLink works with both <a href="https://www.alsa-project.org/wiki/Main_Page">ALSA</a> and <a href="https://www.freedesktop.org/wiki/Software/PulseAudio/">PulseAudio</a>.</li>
  <li>If your system uses <a href="https://pipewire.org/">PipeWire</a>, make sure the <strong>PulseAudio compatibility layer</strong> is enabled so <code>pulsectl</code> can function correctly.</li>
  <li>ALSA Loopback must be enabled for audio routing. See: <a href="https://www.alsa-project.org/wiki/Loopback_Device">ALSA Loopback Device</a>.</li>
</ul>


<h2>Installation and Setup</h2>

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

<ol>
  <li>Activate your virtual environment:
    <pre><code>source venv/bin/activate</code></pre>
  </li>

  <li>Run ZPTTLink:
    <pre><code>python -m zpttlink</code></pre>
  </li>

  <li>Available commands:
    <ul>
      <li><code>help</code> — Displays available commands and usage info</li>
      <li><code>q</code> or <code>quit</code> — Safely exits the program</li>
    </ul>
  </li>

  <li>Launch Zello inside BlueStacks or Waydroid:
    <ul>
      <li>Assign the same hotkey in Zello (e.g., F8 or F9)</li>
      <li>Select the virtual audio driver as the microphone input</li>
    </ul>
  </li>

  <li>Press the PTT button on your radio cable (e.g., AIOC).  
  ZPTTLink will detect it, simulate a keypress, and Zello will transmit your audio.</li>
</ol>

<h2>How It Works</h2>

<p>ZPTTLink listens to the USB serial signal from your radio cable. When activated, it simulates a keypress or mouse event to trigger Zello in BlueStacks or Waydroid. Audio from your radio is routed using the virtual audio driver, creating a seamless RF-to-Zello link.</p>

<h2>License</h2>

<p>MIT License</p>

<h2>Contributing</h2>

<p>Pull requests are welcome. Open an issue first to discuss ideas or report bugs.</p>

<h2>Related Projects</h2>

<ul>
  <li><a href="https://github.com/skuep/AIOC">AIOC – All-In-One Cable</a></li>
  <li><a href="https://github.com/ExistentialAudio/BlackHole">BlackHole (macOS)</a></li>
  <li><a href="https://github.com/alsa-project/alsa-utils">ALSA Utils / Loopback (Linux)</a></li>
  <li><a href="https://github.com/bluestacks">BlueStacks</a></li>
  <li><a href="https://github.com/waydroid">Waydroid</a></li>
  <li><a href="https://github.com/vb-audio-software">VB-Audio (VB-Cable)</a></li>
</ul>

<h2>Acknowledgments</h2>

<p>Portions of this project are based on or inspired by the <a href="https://github.com/skuep/AIOC">AIOC (All-in-one-Cable)</a>.<br>  
Zello® for Android is a trademark of Zello Inc., Android™ is a trademark of Google LLC, and both are used here solely for interoperability purposes.  
All other trademarks are the property of their respective owners.</p>

