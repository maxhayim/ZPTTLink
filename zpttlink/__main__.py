import json
import os
import sys
import serial
import sounddevice as sd
from pynput.keyboard import Controller, Key
import platform

CONFIG_FILE = "config.json"

# Load configuration
def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "com_port": "COM3" if platform.system() == "Windows" else "/dev/ttyUSB0",
            "audio_input": "AIOC Microphone",
            "audio_output": "AIOC Speaker",
            "ptt_hotkey": "F9"
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)
        print(f"[INFO] No config.json found. Created default at {CONFIG_FILE}")
        return default_config

    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load {CONFIG_FILE}: {e}")
        sys.exit(1)

# Check audio devices
def check_audio_devices(config):
    devices = sd.query_devices()
    input_found = any(config["audio_input"] in str(d) for d in devices)
    output_found = any(config["audio_output"] in str(d) for d in devices)

    if not input_found:
        print(f"[WARNING] Input device '{config['audio_input']}' not found.")
    if not output_found:
        print(f"[WARNING] Output device '{config['audio_output']}' not found.")

# Handle PTT (simulated for now)
def handle_ptt(config):
    keyboard = Controller()
    hotkey = config["ptt_hotkey"]

    print(f"[INFO] Pressing PTT hotkey: {hotkey}")
    keyboard.press(hotkey)
    keyboard.release(hotkey)

# Main function
def main():
    config = load_config()
    print(f"[INFO] Loaded config: {config}")

    check_audio_devices(config)

    try:
        ser = serial.Serial(config["com_port"], 9600, timeout=1)
        print(f"[INFO] Listening on {config['com_port']}...")
    except serial.SerialException:
        print(f"[ERROR] Could not open COM port {config['com_port']}.")
        return

    try:
        while True:
            if ser.in_waiting:
                data = ser.readline().decode(errors="ignore").strip()
                if "PTT" in data:
                    print("[DEBUG] PTT signal received")
                    handle_ptt(config)
    except KeyboardInterrupt:
        print("\n[INFO] Exiting...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
