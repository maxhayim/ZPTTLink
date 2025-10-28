import argparse
import json
import logging
import os
import platform
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

import serial
from serial.tools import list_ports

# Optional: audio device listing (no routing; KISS)
try:
    import sounddevice as sd
except Exception:
    sd = None

# Keystroke injection (global)
from pynput.keyboard import Controller, Key

APP_NAME = "zpttlink"
DEFAULT_KEY = "F9"
DEFAULT_LOGFILE = "zpttlink.log"
DEFAULT_CONFIG_FILE = "config.json"

stop_event = threading.Event()
keyboard = None
logger = None

# Map common hotkey names to pynput Key values
KEYMAP = {
    "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4, "f5": Key.f5,
    "f6": Key.f6, "f7": Key.f7, "f8": Key.f8, "f9": Key.f9, "f10": Key.f10,
    "f11": Key.f11, "f12": Key.f12,
    "esc": Key.esc, "escape": Key.esc,
    "space": Key.space,
    "enter": Key.enter, "return": Key.enter,
    "tab": Key.tab,
    "shift": Key.shift, "ctrl": Key.ctrl, "alt": Key.alt, "cmd": Key.cmd, "win": Key.cmd,
}

def parse_hotkey(name: str):
    """
    Accepts things like 'F8', 'f9', 'ENTER', or single characters like 'x'.
    Returns a pynput Key or a string character usable by keyboard.press().
    """
    if not name:
        return Key.f9
    s = name.strip().lower()
    if s in KEYMAP:
        return KEYMAP[s]
    # F1..F24 pattern
    if s.startswith("f") and s[1:].isdigit():
        return KEYMAP.get(s, Key.f9)
    # Single character fallback
    if len(s) == 1:
        return s
    # Default
    return Key.f9

# ------------------- Logging -------------------
def setup_logging(level="INFO", logfile=DEFAULT_LOGFILE):
    lg = logging.getLogger(APP_NAME)
    lg.setLevel(level.upper())
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    lg.addHandler(ch)

    # File (best-effort)
    try:
        fh = RotatingFileHandler(logfile, maxBytes=512 * 1024, backupCount=2)
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except Exception:
        pass

    return lg

# ------------------- Config (JSON) -------------------
DEFAULT_CONFIG = {
    "com_port": "COM3" if platform.system() == "Windows" else "/dev/ttyUSB0",
    "audio_input": "AIOC Microphone",
    "audio_output": "AIOC Speaker",
    "ptt_hotkey": DEFAULT_KEY,
    "logging": {
        "level": "INFO",
        "file": DEFAULT_LOGFILE
    },
    "debounce": {
        "press_ms": 30,
        "release_ms": 60
    },
    # Hints for auto-detect if com_port is empty
    "serial_autodetect_hints": ["usb", "ttyacm", "ttyusb", "usbmodem", "usbserial", "aioc", "cm108"],
}

def ensure_config_exists(path: str):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print(f"[INFO] Created default configuration at {path}")

def load_config(path: str):
    ensure_config_exists(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # shallow merge defaults to fill any missing keys
        cfg = DEFAULT_CONFIG.copy()
        for k, v in (data or {}).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                merged = cfg[k].copy()
                merged.update(v)
                cfg[k] = merged
            else:
                cfg[k] = v
        return cfg
    except Exception as e:
        print(f"[ERROR] Failed to read '{path}': {e}")
        print("[ERROR] Using internal defaults.")
        return DEFAULT_CONFIG.copy()

# ------------------- Serial helpers -------------------
def list_serial_ports():
    return list(list_ports.comports())

def autodetect_serial(match_substrings):
    ports = list_serial_ports()
    ranked = []
    for p in ports:
        score = 0
        text = f"{p.device} {p.description} {p.hwid}".lower()
        for s in match_substrings:
            if s.lower() in text:
                score += 1
        ranked.append((score, p.device))
    ranked.sort(reverse=True)
    return ranked[0][1] if ranked else None

# ------------------- Audio listing -------------------
def list_audio_devices():
    if not sd:
        print("sounddevice not available; cannot list audio devices.")
        return
    try:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            name = dev.get("name")
            host = dev.get("hostapi")
            print(f"[{i}] {name} (hostapi={host})")
    except Exception as e:
        print(f"Failed to query audio devices: {e}")

# ------------------- Keyboard control -------------------
def press_key(hotkey, dry=False):
    if dry:
        logger.debug(f"[DRY] press {hotkey}")
        return
    try:
        keyboard.press(hotkey)
    except Exception as e:
        logger.error(f"Keyboard press failed: {e}")
        raise

def release_key(hotkey, dry=False):
    if dry:
        logger.debug(f"[DRY] release {hotkey}")
        return
    try:
        keyboard.release(hotkey)
    except Exception as e:
        logger.error(f"Keyboard release failed: {e}")
        raise

def make_handlers(hotkey, dry_run=False):
    def on_press():
        logger.info("PTT DOWN -> key down")
        press_key(hotkey, dry=dry_run)
    def on_release():
        logger.info("PTT UP   -> key up")
        release_key(hotkey, dry=dry_run)
    return on_press, on_release

# ------------------- PTT loop (modem lines) -------------------
def read_ptt_loop(ser, on_press, on_release, press_ms=30, release_ms=60):
    """
    Treat any asserted modem line (CTS/DSR/CD) as PTT down.
    Debounce in both directions.
    """
    was_down = False
    last_change = 0.0
    try:
        while not stop_event.is_set():
            down = bool(ser.cts or ser.dsr or ser.cd)
            now = time.time() * 1000.0
            if down != was_down:
                needed = press_ms if down else release_ms
                if (now - last_change) >= needed:
                    was_down = down
                    last_change = now
                    if down:
                        on_press()
                    else:
                        on_release()
            time.sleep(0.005)  # 5 ms tick
    finally:
        if was_down:
            on_release()

# ------------------- Signals -------------------
def handle_stop_signal(*_):
    logger.info("Shutting down...")
    stop_event.set()

def wayland_warning_if_needed():
    if platform.system() == "Linux" and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        logger.warning(
            "Wayland session detected. Global key injection may be blocked.\n"
            "If PTT doesn’t work, try an X11 session or a tool like 'ydotool'."
        )

# ------------------- Main -------------------
def main():
    parser = argparse.ArgumentParser(prog="zpttlink", description="ZPTTLink core (KISS)")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help=f"Path to config JSON (default: {DEFAULT_CONFIG_FILE})")
    parser.add_argument("--key", help="Hotkey to send to Zello (e.g., F8/F9/ENTER or a single letter)")
    parser.add_argument("--serial", help="Serial port (overrides config/autodetect)")
    parser.add_argument("--baud", type=int, default=9600, help="Serial baud rate (default: 9600)")
    parser.add_argument("--list-serial", action="store_true", help="List serial ports and exit")
    parser.add_argument("--list-audio", action="store_true", help="List audio devices and exit")
    parser.add_argument("--dry-run", action="store_true", help="Log PTT events but do not press keys")
    parser.add_argument("--log-level", default=None, help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    cfg = load_config(args.config)

    # Logging
    log_level = args.log_level or cfg.get("logging", {}).get("level", "INFO")
    logfile = cfg.get("logging", {}).get("file", DEFAULT_LOGFILE)
    global logger
    logger = setup_logging(level=log_level, logfile=logfile)

    logger.info("Starting ZPTTLink core...")
    wayland_warning_if_needed()

    # Lists & exit
    if args.list_serial:
        ports = list_serial_ports()
        if not ports:
            print("No serial ports found.")
        else:
            for p in ports:
                print(f"{p.device:20}  {p.description}  [{p.hwid}]")
        return

    if args.list_audio:
        list_audio_devices()
        return

    # Keyboard init (with permission hints)
    global keyboard
    try:
        keyboard = Controller()
    except Exception as e:
        logger.error(
            "Keyboard controller failed to initialize.\n"
            "- macOS: enable Terminal/iTerm under System Settings → Privacy & Security → Accessibility.\n"
            "- Linux/Wayland: global key injection may be blocked; consider X11 or ydotool."
        )
        raise e

    # Determine hotkey
    hotkey_name = (args.key or cfg.get("ptt_hotkey") or DEFAULT_KEY)
    hotkey_obj = parse_hotkey(hotkey_name)
    logger.info(f"Hotkey set to: {hotkey_name}")

    # Serial port selection
    serial_port = args.serial or cfg.get("com_port") or ""
    if not serial_port:
        hint_list = cfg.get("serial_autodetect_hints", [])
        serial_port = autodetect_serial(hint_list)
        if serial_port:
            logger.info(f"Auto-detected serial port: {serial_port}")
        else:
            logger.error("No serial port specified and auto-detect found none. Use --serial or set 'com_port' in config.json.")
            sys.exit(2)

    baud = args.baud

    # Open serial
    try:
        ser = serial.Serial(serial_port, baudrate=baud, timeout=0)
    except Exception as e:
        logger.error(f"Failed to open serial port {serial_port}: {e}")
        sys.exit(3)

    # Quick audio “ready” log (KISS – no routing here)
    logger.info("✅ Audio system ready")
    logger.info(f"✅ PTT system ready (listening on {serial_port}, hotkey={hotkey_name}, dry_run={args.dry_run})")

    # Handlers & thread
    press_ms = int(cfg.get("debounce", {}).get("press_ms", 30))
    release_ms = int(cfg.get("debounce", {}).get("release_ms", 60))
    on_press, on_release = make_handlers(hotkey_obj, dry_run=args.dry_run)

    # Signals
    signal.signal(signal.SIGINT, handle_stop_signal)
    try:
        signal.signal(signal.SIGTERM, handle_stop_signal)
    except Exception:
        pass  # Not all platforms have SIGTERM

    t = threading.Thread(target=read_ptt_loop, args=(ser, on_press, on_release, press_ms, release_ms), daemon=True)
    t.start()

    logger.info("ZPTTLink is running successfully! (Ctrl+C to exit)")

    # Wait for stop
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    finally:
        # Ensure key up
        try:
            on_release()
        except Exception:
            pass
        # Close serial
        try:
            ser.close()
        except Exception:
            pass
        logger.info("ZPTTLink stopped. Goodbye.")
