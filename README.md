ZPTTLink
========

ZPTTLink is an open-source, cross-platform application that bridges Zello (running inside BlueStacks) with radio gateway hardware like the AIOC (All-In-One Cable): https://github.com/skuep/AIOC. It enables seamless Push-to-Talk (PTT) control and audio routing, allowing users to link RF radios to Zello using only a desktop computer.

This tool is ideal for GMRS and ham radio operators, emergency communications volunteers, and hobbyists who want to build a software-based radio gateway.

Features
--------

- Compatible with AIOC, CM108-based, and other USB serial/audio radio cables
- Detects PTT signals via USB serial
- Simulates keypresses or mouse events to trigger Zello’s Push-to-Talk
- Cross-platform support for Windows and macOS
- GUI for selecting serial ports, audio devices, and hotkey assignment
- Audio routing via VB-Cable (Windows) or BlackHole (macOS)

Requirements
------------

- AIOC or compatible USB PTT/audio interface
- Python 3.8 or newer
- Zello installed inside BlueStacks
- Virtual audio driver:
  - VB-Cable: https://vb-audio.com/Cable/
  - BlackHole: https://existential.audio/blackhole/

Installation and Setup
----------------------

1. Install Python:
   - Windows: https://www.python.org/downloads/windows
   - macOS: Use Homebrew with: brew install python

2. Install virtual audio driver:
   - Windows: Install VB-Cable from https://vb-audio.com/Cable/
   - macOS: Install BlackHole from https://existential.audio/blackhole/

3. Clone the repository:
   git clone https://github.com/maxhayim/ZPTTLink.git
   cd ZPTTLink

4. Create and activate a virtual environment:
   - Windows:
     python -m venv venv
     venv\Scripts\activate
   - macOS:
     python3 -m venv venv
     source venv/bin/activate

5. Install dependencies:
   pip install -r requirements.txt

Usage
-----

1. Run the app:
   python src/main.py

2. In the GUI:
   - Select your USB serial port (e.g., COM3 or /dev/tty.usbmodem)
   - Choose audio input and output devices
   - Set a hotkey (e.g., F8)

3. Launch Zello inside BlueStacks:
   - Go to Zello settings and assign the same hotkey (e.g., F8)
   - Select the virtual audio driver as the microphone input

4. Press the PTT button on your radio cable. ZPTTLink will detect it, simulate a keypress, and Zello will transmit your audio.

How It Works
------------

ZPTTLink listens to the USB serial signal from your radio cable. When activated, it simulates a keypress or mouse event to trigger Zello in BlueStacks. Audio from your radio is routed using the virtual audio driver, creating a seamless RF-to-Zello link.

License
-------

MIT License

Contributing
------------

Pull requests are welcome. Open an issue first to discuss ideas or report bugs.

Related Projects
----------------

AIOC - All-In-One Cable for Ham Radio: https://github.com/skuep/AIOC
