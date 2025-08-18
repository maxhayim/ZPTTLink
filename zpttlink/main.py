import argparse
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

# ---- Config loader: tomllib (3.11+) or tomli (<=3.10) ----
try:
    import tomllib  # Python 3.11+
    def load_toml_bytes(b: bytes):
        return tomllib.loads(b.decode("utf-8"))
except Exception:
    try:
        import tomli  # Python 3.8–3.10 (add 'tomli' to requirements.txt)
        def load_toml_bytes(b: bytes):
            return tomli.loads(b.decode("utf-8"))
    except Exception:
        tomli = None
        tomllib = None
        def load_toml_bytes(_b: bytes):
            return {}

# ---- Optional audio device listing (no routing; KISS) ----
try:
    import sounddevice as sd
except Exception:
    sd = None

# ---- Keystroke injection (global) ----
from pynput.keyboard import Controller, Key

APP_NAME = "zpttlink"
DEFAULT_KEY = "f9"
DEFAULT_LOGFILE = "zpttlink.log"

stop_event = threading.Event()
keyboard = None
logger = None

KEYMAP = {
    "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4, "f5": Key.f5,
    "f6": Key.f6, "f7": Key.f7, "f8": Key.f8, "f9": Key.f9, "f10": Key.f10,
    "f11": Key.f11, "f12": Key.f12,
    # add more if you like
}

# ------------------- Logging -------------------
def setup_logging(level="INFO", logfile=DEFAULT_LOGFILE):
    lg = logging.getLogger(APP_NAME)
    lg.setLevel(level.upper())
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    lg.addHandler(ch)

    try:
        fh = RotatingFileHandler(logfile, maxBytes=512 * 1024, backupCount=2)
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except Exception:
        # File logging not critical
        pass
    return lg

# ------------------- Config -------------------
DEFAULT_CONFIG = {
    "ptt": {
        "key": DEFAULT_KEY,
    },
    "serial": {
        "port": "",
        "match": ["usb", "ttyacm", "ttyusb", "usbmodem", "usbserial"],  # auto-detect hints
        "baudrate": 9600,
    },
    "debounce": {
        "press_ms": 30,
        "release_ms": 60,
    },
    "audio": {
        "input_match":  ["AIOC", "VB-Audio", "BlackHole", "ALSA"],
        "output_match": ["AIOC", "VB-Audio", "BlackHole", "ALSA"],
    },
    "logging": {
        "level": "INFO",
        "file": DEFAULT_LOGFILE,
    },
}

def load_config(path="config.toml"):
    cfg = DEFAULT_CONFIG.copy()
    if os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                data = load_toml_bytes(f.read())
            # shallow merge (KISS)
            for section, values in (data or {}).items():
                if isinstance(values, dict):
                    cfg.setdefault(section, {})
                    cfg[section].update(values)
                else:
                    cfg[section] = values
        except Exception:
            # Non-fatal: keep defaults
            pass
    return cfg

# ------------------- Serial helpers -------------------
def list_serial_ports():
    ports = list(list_ports.comports())
    return ports

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
def key_down(k, dry=False):
    if dry:
        logger.debug(f"[DRY] key_down({k})")
        return
    try:
        keyboard.press(KEYMAP.get(k.lower(), Key.f9))
    except Exception as e:
        logger.error(f"Keyboard control failed on key_down: {e}")
        raise

def key_up(k, dry=False):
    if dry:
        logger.debug(f"[DRY] key_up({k})")
        return
    try:
        keyboard.release(KEYMAP.get(k.lower(), Key.f9))
    except Exception as e:
        logger.error(f"Keyboard control failed on key_up: {e}")
        raise

def make_handlers(key_name, dry_run=False):
    def on_press():
        logger.info("PTT DOWN -> key down")
        key_down(key_name, dry=dry_run)
    def on_release():
        logger.info("PTT UP   -> key up")
        key_up(key_name, dry=dry_run)
    return on_press, on_release

# ------------------- PTT loop (modem lines) -------------------
def read_ptt_loop(ser, on_press, on_release, press_ms=30, release_ms=60):
    was_down = False
    last_change = 0.0
    try:
        while not stop_event.is_set():
            # Consider any asserted modem line as “PTT down”
            down = bool(ser.cts or ser.dsr or ser.cd)
            now = time.time() * 1000.0
            if down != was_down:
                # apply debounce depending on direction
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
        # Make sure we release the key if we exit while down
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

# ------------------- Optional dependency checks -------------------
def check_optional_deps():
    """
    Warn clearly if platform-specific optional pieces are missing or likely misconfigured.
    Keeps runtime KISS (no hard failure unless absolutely required).
    """
    osname = platform.system()

    # sounddevice is useful for listing devices and confirming PortAudio backends
    if sd is None:
        logger.warning(
            "Python 'sounddevice' not available; audio device listing is disabled.\n"
            "Install with: pip install sounddevice\n"
            "Windows/macOS: also install your virtual audio driver (VB-Cable/BlackHole).\n"
            "Linux: ensure ALSA and PortAudio libs are present."
        )
    else:
        # On Linux, gently hint about ALSA loopback if not present
        if osname == "Linux":
            # Heuristic check for ALSA loopback presence
            loop_candidates = ["/dev/snd/loop0", "/proc/asound/Loopback", "/proc/asound/cards"]
            found_loop = any(os.path.exists(p) and ("Loopback" in open(p).read() if p.endswith("cards") else True)
                             for p in loop_candidates if os.path.exists(p))
            if not found_loop:
                logger.warning(
                    "ALSA Loopback not detected. For virtual routing, enable it with:\n"
                    "  sudo modprobe snd-aloop\n"
                    "To load at boot, add 'snd-aloop' to /etc/modules-load.d/alsa-loopback.conf"
                )

    if osname == "Darwin":
        # pyobjc isn’t strictly required for this KISS build, but it’s a common dependency for macOS integrations.
        try:
            import objc  # noqa: F401
        except Exception:
            logger.warning(
                "macOS: 'pyobjc' not found. If you encounter macOS-specific integration issues, install it:\n"
                "  pip install pyobjc"
            )
        logger.info(
           
from pynput.keyboard import Controller, Key

APP_NAME = "zpttlink"
DEFAULT_KEY = "f9"
DEFAULT_LOGFILE = "zpttlink.log"

stop_event = threading.Event()
keyboard = None
logger = None

KEYMAP = {
    "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4, "f5": Key.f5,
    "f6": Key.f6, "f7": Key.f7, "f8": Key.f8, "f9": Key.f9, "f10": Key.f10,
    "f11": Key.f11, "f12": Key.f12,
    # add more if you like
}

# ------------------- Logging -------------------
def setup_logging(level="INFO", logfile=DEFAULT_LOGFILE):
    lg = logging.getLogger(APP_NAME)
    lg.setLevel(level.upper())
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    lg.addHandler(ch)

    try:
        fh = RotatingFileHandler(logfile, maxBytes=512 * 1024, backupCount=2)
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except Exception:
        # File logging not critical
        pass
    return lg

# ------------------- Config -------------------
DEFAULT_CONFIG = {
    "ptt": {
        "key": DEFAULT_KEY,
    },
    "serial": {
        "port": "",
        "match": ["usb", "ttyacm", "ttyusb", "usbmodem", "usbserial"],  # auto-detect hints
        "baudrate": 9600,
    },
    "debounce": {
        "press_ms": 30,
        "release_ms": 60,
    },
    "audio": {
        "input_match":  ["AIOC", "VB-Audio", "BlackHole", "ALSA"],
        "output_match": ["AIOC", "VB-Audio", "BlackHole", "ALSA"],
    },
    "logging": {
        "level": "INFO",
        "file": DEFAULT_LOGFILE,
    },
}

def load_config(path="config.toml"):
    cfg = DEFAULT_CONFIG.copy()
    if os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                data = load_toml_bytes(f.read())
            # shallow merge (KISS)
            for section, values in (data or {}).items():
                if isinstance(values, dict):
                    cfg.setdefault(section, {})
                    cfg[section].update(values)
                else:
                    cfg[section] = values
        except Exception:
            # Non-fatal: keep defaults
            pass
    return cfg

# ------------------- Serial helpers -------------------
def list_serial_ports():
    ports = list(list_ports.comports())
    return ports

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
def key_down(k, dry=False):
    if dry:
        logger.debug(f"[DRY] key_down({k})")
        return
    try:
        keyboard.press(KEYMAP.get(k.lower(), Key.f9))
    except Exception as e:
        logger.error(f"Keyboard control failed on key_down: {e}")
        raise

def key_up(k, dry=False):
    if dry:
        logger.debug(f"[DRY] key_up({k})")
        return
    try:
        keyboard.release(KEYMAP.get(k.lower(), Key.f9))
    except Exception as e:
        logger.error(f"Keyboard control failed on key_up: {e}")
        raise

def make_handlers(key_name, dry_run=False):
    def on_press():
        logger.info("PTT DOWN -> key down")
        key_down(key_name, dry=dry_run)
    def on_release():
        logger.info("PTT UP   -> key up")
        key_up(key_name, dry=dry_run)
    return on_press, on_release

# ------------------- PTT loop (modem lines) -------------------
def read_ptt_loop(ser, on_press, on_release, press_ms=30, release_ms=60):
    was_down = False
    last_change = 0.0
    try:
        while not stop_event.is_set():
            # Consider any asserted modem line as “PTT down”
            down = bool(ser.cts or ser.dsr or ser.cd)
            now = time.time() * 1000.0
            if down != was_down:
                # apply debounce depending on direction
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
        # Make sure we release the key if we exit while down
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
    # Parse CLI args
    parser = argparse.ArgumentParser(prog="zpttlink", description="ZPTTLink core (KISS)")
    parser.add_argument("--config", default="config.toml", help="Path to config TOML (default: config.toml)")
    parser.add_argument("--key", help="Hotkey to send to Zello (e.g., F8/F9)")
    parser.add_argument("--serial", help="Serial port (overrides auto-detect)")
    parser.add_argument("--list-serial", action="store_true", help="List serial ports and exit")
    parser.add_argument("--list-audio", action="store_true", help="List audio devices and exit")
    parser.add_argument("--dry-run", action="store_true", help="Log PTT events but do not press keys")
    parser.add_argument("--log-level", default=None, help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    cfg = load_config(args.config)

    # Logging
    log_level = args.log_level or cfg["logging"].get("level", "INFO")
    logfile = cfg["logging"].get("file", DEFAULT_LOGFILE)
    global logger
    logger = setup_logging(level=log_level, logfile=logfile)

    logger.info("Starting ZPTTLink core...")

    # Wayland heads-up
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

    # Determine key
    key_name = (args.key or cfg["ptt"].get("key") or DEFAULT_KEY).lower()

    # Serial port selection
    serial_port = args.serial or cfg["serial"].get("port") or ""
    if not serial_port:
        serial_port = autodetect_serial(cfg["serial"].get("match", []))
        if serial_port:
            logger.info(f"Auto-detected serial port: {serial_port}")
        else:
            logger.error("No serial port specified and auto-detect found none. Use --serial or plug your device.")
            sys.exit(2)

    baud = int(cfg["serial"].get("baudrate", 9600))

    # Open serial
    try:
        ser = serial.Serial(serial_port, baudrate=baud, timeout=0)
    except Exception as e:
        logger.error(f"Failed to open serial port {serial_port}: {e}")
        sys.exit(3)

    # Quick audio “ready” log (KISS – no routing here)
    logger.info("✅ Audio system ready")
    logger.info(f"✅ PTT system ready (listening on {serial_port}, key={key_name.upper()}, dry_run={args.dry_run})")

    # Handlers & thread
    press_ms = int(cfg["debounce"].get("press_ms", 30))
    release_ms = int(cfg["debounce"].get("release_ms", 60))
    on_press, on_release = make_handlers(key_name, dry_run=args.dry_run)

    # Signals
    signal.signal(signal.SIGINT, handle_stop_signal)
    try:
        signal.signal(signal.SIGTERM, handle_stop_signal)
    except Exception:
        pass  # Not all platforms have SIGTERM

    t = threading.Thread(target=read_ptt_loop, args=(ser, on_press, on_release, press_ms, release_ms), daemon=True)
    t.start()

    logger.info("ZPTTLink is running successfully!")

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

if __name__ == "__main__":
    main()
