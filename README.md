# ZPTTLink

**ZPTTLink** is an open-source, cross-platform utility that bridges **Zello** (running inside **BlueStacks**) with ham radio gateway hardware like the **AIOC (All-In-One Cable)**. It enables seamless **Push-to-Talk (PTT)** control and **audio routing**, allowing RF radios to interface directly with Zello over the internet.

---

## Purpose

ZPTTLink was built for GMRS, ham radio, and emergency communications users who want to connect their radio hardware to Zello using consumer hardware and open tools. It's ideal for building Zello-linked RF gateways with full control from a single desktop app.

---

## Key Features

- **PTT Detection**  
  Listens to hardware PTT signals over USB serial and triggers push-to-talk inside Zello via key or mouse emulation.

-  **Audio Routing**  
  Connects audio from devices like the AIOC into BlueStacks so Zello can transmit and receive properly.

- **Cross-Platform GUI**  
  Works on **Windows and macOS** with easy selection of COM ports, hotkeys, and audio interfaces.

- **BlueStacks Integration**  
  Automates or simulates keypress/mouse input into Zello running in the BlueStacks emulator.

- **Hardware Support**  
  Compatible with AIOC, CM108-based USB sound cards, and other serial/audio PTT devices.

---

## Installation

### Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/ZPTTLink.git
cd ZPTTLink
