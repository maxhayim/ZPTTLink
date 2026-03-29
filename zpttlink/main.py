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

try:
    import numpy as np
except Exception:
    np = None

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import usb.core
    import usb.util
except Exception:
    usb = None

from pynput.keyboard import Controller, Key

APP_NAME = "zpttlink"
DEFAULT_KEY = "F9"
DEFAULT_LOGFILE = "zpttlink.log"
DEFAULT_CONFIG_FILE = "config.json"

stop_event = threading.Event()
keyboard = None
logger = None
audio_stream = None
_last_level_log = 0.0

KEYMAP = {
    "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4,
    "f5": Key.f5, "f6": Key.f6, "f7": Key.f7, "f8": Key.f8,
    "f9": Key.f9, "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
    "esc": Key.esc, "escape": Key.esc,
    "space": Key.space,
    "enter": Key.enter, "return": Key.enter,
    "tab": Key.tab,
    "shift": Key.shift, "ctrl": Key.ctrl, "alt": Key.alt, "cmd": Key.cmd, "win": Key.cmd,
}


def parse_hotkey(name):
    if not name:
        return Key.f9
    s = str(name).strip().lower()
    if s in KEYMAP:
        return KEYMAP[s]
    if s.startswith("f") and s[1:].isdigit():
        return KEYMAP.get(s, Key.f9)
    if len(s) == 1:
        return s
    return Key.f9


DEFAULT_CONFIG = {
    "radio_type": "auto",
    "com_port": "COM3" if platform.system() == "Windows" else "/dev/ttyUSB0",
    "baud": 9600,

    "audio_input_index": None,
    "audio_output_index": None,

    "ptt_hotkey": DEFAULT_KEY,
    "ptt_output": "dtr",
    "ptt_active_low": False,
    "disable_hotkey": True,
    "force_serial_ptt": True,
    "ignore_initial_ptt_state": True,

    "cm108": {
        "vendor_id": 0x0D8C,
        "product_id": None,
        "gpio_mask": 0x04,
        "active_low": False
    },

    "logging": {
        "level": "INFO",
        "file": DEFAULT_LOGFILE
    },

    "debounce": {
        "press_ms": 30,
        "release_ms": 60
    },

    "vox": {
        "enabled": True,
        "threshold": 0.003,
        "attack_ms": 20,
        "release_ms": 80,
        "hang_ms": 120,
        "log_levels": True
    },

    "audio": {
        "tx_gain": 0.08,
        "samplerate": 48000,
        "limit": 0.90,
        "dc_block": True
    },

    "serial_autodetect_hints": [
        "usb",
        "ttyacm",
        "ttyusb",
        "usbmodem",
        "usbserial",
        "aioc",
        "cm108",
        "digirig"
    ]
}


def merge_defaults(defaults, data):
    if not isinstance(defaults, dict):
        return data if data is not None else defaults
    result = defaults.copy()
    if not isinstance(data, dict):
        return result
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = merge_defaults(result[k], v)
        else:
            result[k] = v
    return result


def ensure_config_exists(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
            f.write("\n")
        print(f"[INFO] Created default configuration at {path}")


def load_config(path):
    ensure_config_exists(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return merge_defaults(DEFAULT_CONFIG, data)
    except Exception as e:
        print(f"[ERROR] Failed to read '{path}': {e}")
        print("[ERROR] Using internal defaults.")
        return merge_defaults(DEFAULT_CONFIG, {})


def setup_logging(level="INFO", logfile=DEFAULT_LOGFILE):
    lg = logging.getLogger(APP_NAME)
    lg.setLevel(level.upper())
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")

    if lg.handlers:
        lg.handlers.clear()

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    lg.addHandler(ch)

    try:
        fh = RotatingFileHandler(logfile, maxBytes=512 * 1024, backupCount=2)
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except Exception:
        pass

    return lg


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


def _audio_role_label(dev):
    in_ch = int(dev.get("max_input_channels", 0) or 0)
    out_ch = int(dev.get("max_output_channels", 0) or 0)

    if in_ch > 0 and out_ch > 0:
        return "Input+Output / RX+TX"
    if in_ch > 0:
        return "Input / RX"
    if out_ch > 0:
        return "Output / TX"
    return "No I/O"


def list_audio_devices():
    if not sd:
        print("sounddevice not available; cannot list audio devices.")
        return
    try:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            name = dev.get("name")
            role = _audio_role_label(dev)
            print(f"[{i}] {name} ({role})")
    except Exception as e:
        print(f"Failed to query audio devices: {e}")


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


def apply_active_low(state, active_low):
    return (not state) if active_low else state


class RadioInterfaceBase:
    name = "base"

    def open(self):
        pass

    def ptt_on(self, dry=False):
        pass

    def ptt_off(self, dry=False):
        pass

    def close(self):
        pass


class DigiRigRadio(RadioInterfaceBase):
    name = "digirig"

    def __init__(self, serial_port, baud, ptt_output="dtr", active_low=False):
        self.serial_port = serial_port
        self.baud = baud
        self.ptt_output = (ptt_output or "dtr").lower()
        self.active_low = bool(active_low)
        self.ser = None

    def open(self):
        self.ser = serial.Serial(self.serial_port, baudrate=self.baud, timeout=0)
        try:
            self.ser.dtr = apply_active_low(False, self.active_low)
            self.ser.rts = apply_active_low(False, self.active_low)
            time.sleep(0.1)
        except Exception:
            pass

    def _set(self, logical_state, dry=False):
        if self.ser is None:
            raise RuntimeError("Serial port not open")
        physical_state = apply_active_low(bool(logical_state), self.active_low)

        if dry:
            logger.debug(
                f"[DRY] DigiRig {self.ptt_output.upper()} logical={logical_state} "
                f"physical={physical_state} active_low={self.active_low}"
            )
            return

        if self.ptt_output == "dtr":
            self.ser.dtr = physical_state
        elif self.ptt_output == "rts":
            self.ser.rts = physical_state
        else:
            raise RuntimeError(f"Unsupported ptt_output for DigiRig: {self.ptt_output}")

        logger.info(
            f"Serial PTT {self.ptt_output.upper()} -> {'ON' if logical_state else 'OFF'} "
            f"(physical={'HIGH' if physical_state else 'LOW'}, active_low={self.active_low})"
        )

    def ptt_on(self, dry=False):
        self._set(True, dry=dry)

    def ptt_off(self, dry=False):
        self._set(False, dry=dry)

    def close(self):
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass
        self.ser = None


class CM108Radio(RadioInterfaceBase):
    name = "cm108"

    def __init__(self, vendor_id=0x0D8C, product_id=None, gpio_mask=0x04, active_low=False):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.gpio_mask = int(gpio_mask) & 0xFF
        self.active_low = bool(active_low)
        self.dev = None

    def open(self):
        if usb is None:
            raise RuntimeError("pyusb not installed. Install with: pip install pyusb")
        kwargs = {"idVendor": self.vendor_id}
        if self.product_id is not None:
            kwargs["idProduct"] = self.product_id
        self.dev = usb.core.find(**kwargs)
        if self.dev is None:
            raise RuntimeError(
                f"CM108/CM119 device not found (vendor=0x{self.vendor_id:04x}"
                + (f", product=0x{self.product_id:04x}" if self.product_id is not None else "")
                + ")"
            )

    def _write_gpio(self, logical_state, dry=False):
        if self.dev is None:
            raise RuntimeError("CM108 device not open")

        # Many CM108 node interfaces use inverted logic externally; keep this configurable.
        effective_on = apply_active_low(bool(logical_state), self.active_low)
        value = self.gpio_mask if effective_on else 0x00

        if dry:
            logger.debug(
                f"[DRY] CM108 GPIO logical={logical_state} effective_on={effective_on} "
                f"mask=0x{self.gpio_mask:02x} value=0x{value:02x}"
            )
            return

        # Standard CM108-style HID control transfer used by radio node software.
        self.dev.ctrl_transfer(0x21, 0x09, 0x0200, 0, [value])
        logger.info(
            f"CM108 PTT -> {'ON' if logical_state else 'OFF'} "
            f"(gpio=0x{value:02x}, active_low={self.active_low})"
        )

    def ptt_on(self, dry=False):
        self._write_gpio(True, dry=dry)

    def ptt_off(self, dry=False):
        self._write_gpio(False, dry=dry)

    def close(self):
        self.dev = None


class SignalinkRadio(RadioInterfaceBase):
    name = "signalink"

    def open(self):
        logger.info("Signalink selected: hardware VOX/PTT expected; no software PTT control.")

    def ptt_on(self, dry=False):
        if dry:
            logger.debug("[DRY] Signalink PTT ON (no-op)")
        else:
            logger.info("Signalink PTT ON (no-op)")

    def ptt_off(self, dry=False):
        if dry:
            logger.debug("[DRY] Signalink PTT OFF (no-op)")
        else:
            logger.info("Signalink PTT OFF (no-op)")

    def close(self):
        pass


def choose_radio_type(cfg, args):
    explicit = getattr(args, "radio_type", None)
    if explicit:
        return explicit.lower()

    cfg_type = str(cfg.get("radio_type", "auto")).lower()
    if cfg_type != "auto":
        return cfg_type

    # Auto-detect: prefer CM108 if requested via hints/name, otherwise DigiRig if serial port present.
    port = str(cfg.get("com_port", "")).lower()
    hints = " ".join(cfg.get("serial_autodetect_hints", [])).lower()
    if "cm108" in hints or "aioc" in hints or "cm108" in port or "aioc" in port:
        # Keep auto conservative: if pyusb is present and a CM108-like device exists, use it.
        if usb is not None:
            vendor_id = int(cfg.get("cm108", {}).get("vendor_id", 0x0D8C))
            product_id = cfg.get("cm108", {}).get("product_id", None)
            kwargs = {"idVendor": vendor_id}
            if product_id is not None:
                kwargs["idProduct"] = product_id
            try:
                found = usb.core.find(**kwargs)
                if found is not None:
                    return "cm108"
            except Exception:
                pass

    return "digirig"


def build_radio_backend(cfg, args):
    radio_type = choose_radio_type(cfg, args)

    if radio_type == "cm108":
        cm_cfg = cfg.get("cm108", {})
        vendor_id = int(cm_cfg.get("vendor_id", 0x0D8C))
        product_id = cm_cfg.get("product_id", None)
        gpio_mask = int(cm_cfg.get("gpio_mask", 0x04))
        active_low = bool(cm_cfg.get("active_low", False))
        return CM108Radio(
            vendor_id=vendor_id,
            product_id=product_id,
            gpio_mask=gpio_mask,
            active_low=active_low,
        )

    if radio_type == "signalink":
        return SignalinkRadio()

    # digirig default
    ptt_output = (args.ptt_output or cfg.get("ptt_output") or "dtr").lower()
    if args.ptt_active_low and args.ptt_active_high:
        logger.error("Use only one of --ptt-active-low or --ptt-active-high")
        sys.exit(8)

    if args.ptt_active_low:
        ptt_active_low = True
    elif args.ptt_active_high:
        ptt_active_low = False
    else:
        ptt_active_low = bool(cfg.get("ptt_active_low", False))

    serial_port = args.serial or cfg.get("com_port") or ""
    if not serial_port:
        serial_port = autodetect_serial(cfg.get("serial_autodetect_hints", []))
        if serial_port:
            logger.info(f"Auto-detected serial port: {serial_port}")
        else:
            logger.error("No serial port specified and auto-detect found none.")
            sys.exit(2)

    baud = args.baud if args.baud is not None else int(cfg.get("baud", 9600))

    return DigiRigRadio(
        serial_port=serial_port,
        baud=baud,
        ptt_output=ptt_output,
        active_low=ptt_active_low,
    )


class PTTController:
    def __init__(self, backend, hotkey=None, hotkey_enabled=False, dry_run=False):
        self.backend = backend
        self.hotkey = hotkey
        self.hotkey_enabled = hotkey_enabled
        self.dry_run = dry_run
        self.is_down = False
        self.lock = threading.Lock()

    def down(self, source="unknown"):
        with self.lock:
            if self.is_down:
                return
            self.is_down = True
            logger.info(f"PTT DOWN ({source})")

            if self.hotkey_enabled and self.hotkey is not None:
                logger.info("PTT DOWN -> key down")
                press_key(self.hotkey, dry=self.dry_run)

            self.backend.ptt_on(dry=self.dry_run)

    def up(self, source="unknown"):
        with self.lock:
            if not self.is_down:
                return
            self.is_down = False
            logger.info(f"PTT UP ({source})")

            if self.hotkey_enabled and self.hotkey is not None:
                logger.info("PTT UP -> key up")
                release_key(self.hotkey, dry=self.dry_run)

            self.backend.ptt_off(dry=self.dry_run)


class AudioGate:
    def __init__(self, threshold=0.02, attack_ms=40, release_ms=120, hang_ms=300):
        self.threshold = float(threshold)
        self.attack_ms = int(attack_ms)
        self.release_ms = int(release_ms)
        self.hang_ms = int(hang_ms)

        self.active = False
        self.audio_started_at = None
        self.silence_started_at = None
        self.hang_until = 0.0

    def reset(self):
        self.active = False
        self.audio_started_at = None
        self.silence_started_at = None
        self.hang_until = 0.0

    def process(self, level, now=None):
        now = time.monotonic() if now is None else now
        above = level >= self.threshold

        if above:
            self.silence_started_at = None
            self.hang_until = 0.0
            if self.audio_started_at is None:
                self.audio_started_at = now

            if not self.active and (now - self.audio_started_at) * 1000.0 >= self.attack_ms:
                self.active = True
                return "start"
            return None

        self.audio_started_at = None

        if self.active:
            if self.silence_started_at is None:
                self.silence_started_at = now
                return None

            silence_ms = (now - self.silence_started_at) * 1000.0
            if silence_ms >= self.release_ms:
                if self.hang_until == 0.0:
                    self.hang_until = now + (self.hang_ms / 1000.0)

                if now >= self.hang_until:
                    self.active = False
                    self.silence_started_at = None
                    self.hang_until = 0.0
                    return "stop"

        return None


def rms_level(data):
    if np is None or data is None:
        return 0.0
    try:
        arr = np.asarray(data, dtype=np.float32)
        if arr.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(arr))))
    except Exception:
        return 0.0


def zero_out(outdata):
    try:
        outdata.fill(0)
    except Exception:
        try:
            outdata[:] = 0
        except Exception:
            pass


def sanitize_audio(indata, tx_gain=0.02, limit=0.80, dc_block=True):
    if np is None:
        return indata

    arr = np.asarray(indata, dtype=np.float32)

    if arr.ndim == 2 and arr.shape[1] > 1:
        mono = np.mean(arr, axis=1, dtype=np.float32)
    elif arr.ndim == 2 and arr.shape[1] == 1:
        mono = arr[:, 0]
    else:
        mono = arr.reshape(-1)

    if dc_block and mono.size:
        mono = mono - np.mean(mono, dtype=np.float32)

    mono = mono * np.float32(tx_gain)

    if limit > 0:
        drive = 1.0 / max(limit, 1e-6)
        mono = np.tanh(mono * drive) * np.float32(limit)

    return mono.astype(np.float32).reshape(-1, 1)


def log_runtime_diagnostics():
    if platform.system() != "Linux":
        return

    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower() or "unknown"
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "") or "unknown"
    logger.info(f"Runtime session: {session_type} (desktop={desktop})")

    if session_type == "wayland":
        logger.warning(
            "Wayland session detected. Global key injection may be blocked. "
            "Prefer serial or CM108 PTT with --force-serial-ptt."
        )


def handle_stop_signal(*_):
    logger.info("Shutting down...")
    stop_event.set()


def choose_samplerate(input_index, output_index, default_sr=48000):
    if not sd:
        return default_sr
    try:
        in_info = sd.query_devices(input_index)
        out_info = sd.query_devices(output_index)
        in_sr = in_info.get("default_samplerate") or default_sr
        out_sr = out_info.get("default_samplerate") or default_sr
        if abs(float(in_sr) - float(out_sr)) < 1.0:
            return int(round(float(in_sr)))
    except Exception:
        pass
    return default_sr


def maybe_log_level(level, enabled):
    global _last_level_log
    if not enabled:
        return
    now = time.monotonic()
    if now - _last_level_log >= 0.25:
        logger.info(f"VOX level={level:.6f}")
        _last_level_log = now


def main():
    global keyboard, logger, audio_stream

    parser = argparse.ArgumentParser(prog="zpttlink", description="ZPTTLink 2.1 TX bridge")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE)
    parser.add_argument("--key", help="Hotkey to send to Zello")
    parser.add_argument("--serial", help="Serial port override")
    parser.add_argument("--baud", type=int, default=None)
    parser.add_argument("--radio-type", choices=["auto", "cm108", "digirig", "signalink"], default=None)
    parser.add_argument("--ptt-output", choices=["none", "dtr", "rts"], default=None)
    parser.add_argument("--no-hotkey", action="store_true")
    parser.add_argument("--test-ptt", action="store_true")
    parser.add_argument("--list-serial", action="store_true")
    parser.add_argument("--list-audio", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default=None)

    parser.add_argument("--audio-input-index", type=int, default=None)
    parser.add_argument("--audio-output-index", type=int, default=None)

    parser.add_argument("--vox", action="store_true")
    parser.add_argument("--vox-threshold", type=float, default=None)
    parser.add_argument("--vox-attack-ms", type=int, default=None)
    parser.add_argument("--vox-release-ms", type=int, default=None)
    parser.add_argument("--vox-hang-ms", type=int, default=None)

    parser.add_argument("--ignore-initial-ptt-state", action="store_true")
    parser.add_argument("--force-serial-ptt", action="store_true")
    parser.add_argument("--ptt-active-low", action="store_true")
    parser.add_argument("--ptt-active-high", action="store_true")

    args = parser.parse_args()

    cfg = load_config(args.config)

    log_level = args.log_level or cfg.get("logging", {}).get("level", "INFO")
    logfile = cfg.get("logging", {}).get("file", DEFAULT_LOGFILE)
    logger = setup_logging(level=log_level, logfile=logfile)

    logger.info("Starting ZPTTLink core...")
    log_runtime_diagnostics()

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

    hotkey_name = args.key or cfg.get("ptt_hotkey") or DEFAULT_KEY
    hotkey_obj = parse_hotkey(hotkey_name)

    force_serial_ptt = bool(args.force_serial_ptt or cfg.get("force_serial_ptt", False))
    hotkey_enabled = not (args.no_hotkey or cfg.get("disable_hotkey", False))
    if force_serial_ptt:
        hotkey_enabled = False

    if hotkey_enabled:
        try:
            keyboard = Controller()
        except Exception as e:
            logger.error(
                "Keyboard controller failed to initialize.\n"
                "- macOS: enable Terminal/iTerm under Privacy & Security -> Accessibility.\n"
                "- Wayland: key injection may be blocked; prefer hardware PTT backends."
            )
            raise e
        logger.info(f"Hotkey set to: {hotkey_name}")
    else:
        logger.info("Hotkey injection disabled.")

    backend = build_radio_backend(cfg, args)
    backend.open()
    logger.info(f"Radio backend: {backend.name}")

    ptt = PTTController(
        backend=backend,
        hotkey=hotkey_obj,
        hotkey_enabled=hotkey_enabled,
        dry_run=args.dry_run,
    )

    if args.test_ptt:
        logger.info("Testing PTT for 1 second...")
        ptt.down(source="test")
        time.sleep(1.0)
        ptt.up(source="test")
        logger.info("PTT test complete.")
        try:
            backend.close()
        except Exception:
            pass
        return

    if sd is None or np is None:
        logger.error("sounddevice and numpy are required for audio bridge mode")
        try:
            backend.close()
        except Exception:
            pass
        sys.exit(5)

    signal.signal(signal.SIGINT, handle_stop_signal)
    try:
        signal.signal(signal.SIGTERM, handle_stop_signal)
    except Exception:
        pass

    input_index = args.audio_input_index
    if input_index is None:
        input_index = cfg.get("audio_input_index")

    output_index = args.audio_output_index
    if output_index is None:
        output_index = cfg.get("audio_output_index")

    if input_index is None or output_index is None:
        logger.error("audio_input_index and audio_output_index must be set in config.json")
        try:
            backend.close()
        except Exception:
            pass
        sys.exit(6)

    vox_cfg = cfg.get("vox", {})
    vox_enabled = bool(args.vox or vox_cfg.get("enabled", False))
    vox_threshold = float(args.vox_threshold if args.vox_threshold is not None else vox_cfg.get("threshold", 0.02))
    vox_attack_ms = int(args.vox_attack_ms if args.vox_attack_ms is not None else vox_cfg.get("attack_ms", 40))
    vox_release_ms = int(args.vox_release_ms if args.vox_release_ms is not None else vox_cfg.get("release_ms", 120))
    vox_hang_ms = int(args.vox_hang_ms if args.vox_hang_ms is not None else vox_cfg.get("hang_ms", 300))
    vox_log_levels = bool(vox_cfg.get("log_levels", False))

    audio_cfg = cfg.get("audio", {})
    tx_gain = float(audio_cfg.get("tx_gain", 0.08))
    configured_sr = int(audio_cfg.get("samplerate", 48000))
    limiter = float(audio_cfg.get("limit", 0.90))
    dc_block = bool(audio_cfg.get("dc_block", True))

    logger.info(f"TX input index: {input_index}")
    logger.info(f"TX output index: {output_index}")
    logger.info(
        "TX VOX: "
        + ("enabled" if vox_enabled else "disabled")
        + f" threshold={vox_threshold} attack={vox_attack_ms}ms release={vox_release_ms}ms hang={vox_hang_ms}ms"
    )
    logger.info(
        f"TX gain: {tx_gain}, limiter: {limiter}, dc_block: {dc_block}"
    )

    try:
        in_info = sd.query_devices(input_index)
        out_info = sd.query_devices(output_index)
        logger.info(f"Audio input:  [{input_index}] {in_info.get('name')}")
        logger.info(f"Audio output: [{output_index}] {out_info.get('name')}")
    except Exception:
        pass

    gate = AudioGate(
        threshold=vox_threshold,
        attack_ms=vox_attack_ms,
        release_ms=vox_release_ms,
        hang_ms=vox_hang_ms,
    )

    samplerate = choose_samplerate(input_index, output_index, default_sr=configured_sr)
    logger.info(f"TX samplerate: {samplerate}")

    def audio_callback(indata, outdata, frames, time_info, status):
        if status:
            logger.warning(f"TX callback status: {status}")

        level = rms_level(indata)
        maybe_log_level(level, vox_log_levels)

        try:
            shaped = sanitize_audio(
                indata,
                tx_gain=tx_gain,
                limit=limiter,
                dc_block=dc_block,
            )
            outdata[:] = shaped
        except Exception as e:
            logger.error(f"Audio shaping failed: {e}")
            zero_out(outdata)

        if not vox_enabled:
            return

        action = gate.process(level)
        if action == "start":
            ptt.down(source="vox")
        elif action == "stop":
            ptt.up(source="vox")

    try:
        audio_stream = sd.Stream(
            device=(input_index, output_index),
            samplerate=samplerate,
            channels=1,
            dtype="float32",
            callback=audio_callback,
        )
        audio_stream.start()
        logger.info("TX audio stream active.")
    except Exception as e:
        logger.error(f"Failed to start TX stream: {e}")
        try:
            backend.close()
        except Exception:
            pass
        sys.exit(7)

    logger.info(
        f"PTT system ready (radio_backend={backend.name}, hotkey_enabled={hotkey_enabled}, dry_run={args.dry_run})"
    )
    logger.info("ZPTTLink 2.1 TX bridge is running successfully! (Ctrl+C to exit)")

    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    finally:
        try:
            ptt.up(source="shutdown")
        except Exception:
            pass

        try:
            if audio_stream is not None:
                audio_stream.stop()
                audio_stream.close()
        except Exception:
            pass

        try:
            backend.close()
        except Exception:
            pass

        logger.info("ZPTTLink stopped. Goodbye.")


if __name__ == "__main__":
    main()