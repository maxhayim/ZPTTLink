# ZPTTLink

ZPTTLink is an open-source, cross-platform utility that connects Zello (running inside BlueStacks) to ham radio gateway hardware like the AIOC (All-In-One Cable). It enables real-time Push-to-Talk (PTT) control and audio routing between your radio and Zello using only your desktop computer. This allows radio operators to build digital voice gateways for GMRS, ham radio, or emergency communications.

The AIOC hardware used with ZPTTLink is developed as an open-source project and can be found at https://github.com/skuep/AIOC. It combines audio and PTT over USB and is compatible with various radios through standard mic connectors.

To begin, install Python 3.8 or newer. On Windows, download it from https://www.python.org/downloads/windows and make sure to check the box that says “Add Python to PATH” during installation. On macOS, the easiest way is to install it via Homebrew by running `brew install python` from Terminal.

Next, you need a virtual audio driver to route your radio’s microphone signal into BlueStacks. For Windows, go to https://vb-audio.com/Cable and download VB-Cable. For macOS, use BlackHole from https://existential.audio/blackhole. If you're on macOS, after installing BlackHole, open the “Audio MIDI Setup” app and create a multi-output device that includes BlackHole and your regular audio output so you can hear and send audio at the same time.

Now that your audio routing is in place, download ZPTTLink by opening a terminal or command prompt and running `git clone https://github.com/maxhayim/ZPTTLink.git`. Then navigate into the folder with `cd ZPTTLink`.

Create a virtual Python environment to isolate the project dependencies. On Windows, run `python -m venv venv` followed by `venv\Scripts\activate`. On macOS, use `python3 -m venv venv` and activate it with `source venv/bin/activate`. Once inside the virtual environment, install the required libraries using `pip install -r requirements.txt`.

You can now run the application with `python src/main.py`. A graphical window will appear. In this interface, select your serial port that corresponds to your AIOC device — for example, COM3 on Windows or /dev/tty.usbmodemXXXX on macOS. Then choose the appropriate audio input and output devices, and assign a hotkey (such as F8) that will be used to trigger Zello’s push-to-talk.

Launch BlueStacks and open the Zello app. Go into Zello’s settings, find the Push-to-Talk configuration, and set the same hotkey you chose in ZPTTLink. Also make sure Zello is using the virtual audio cable (VB-Cable or BlackHole) as its microphone input.

With everything configured, press the physical PTT button on your AIOC cable. ZPTTLink will detect the signal over USB serial, simulate a keyboard press to trigger Zello, and send audio through the virtual audio cable into BlueStacks. Your radio is now effectively linked to Zello.

ZPTTLink allows anyone to bridge a physical radio to Zello using open-source tools and minimal hardware. This solution is designed for GMRS operators, ham radio users, emergency communications volunteers, and anyone interested in integrating voice-over-IP with their existing radio setup. The project runs on both Windows and macOS.

ZPTTLink is released under the MIT License. Contributions are welcome via pull request.


