import argparse
import json
import logging
import os
import platform
import queue
import shutil
import signal
import socket
import struct
import subprocess
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

try:
    from pynput.keyboard import Controller, Key
except Exception:
    Controller = None
    Key = None

APP_NAME = "zpttlink"
DEFAULT_KEY = "F9"
DEFAULT_LOGFILE = "zpttlink.log"
DEFAULT_CONFIG_FILE = "config.json"

stop_event = threading.Event()
keyboard = None
logger = None
audio_stream = None
_last_level_log = 0.0

if Key is not None:
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
else:
    KEYMAP = {}

# Linux input-event-codes.h keycodes, for injecting via `ydotool` when pynput's
# key injection is blocked (Wayland compositors reject synthetic global input).
YDOTOOL_KEYCODES = {
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "esc": 1, "escape": 1,
    "space": 57,
    "enter": 28, "return": 28,
    "tab": 15,
    "shift": 42, "ctrl": 29, "alt": 56, "cmd": 125, "win": 125,
    "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34,
    "h": 35, "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49,
    "o": 24, "p": 25, "q": 16, "r": 19, "s": 31, "t": 20, "u": 22,
    "v": 47, "w": 17, "x": 45, "y": 21, "z": 44,
    "0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10,
}


def ydotool_keycode(name):
    if not name:
        return None
    return YDOTOOL_KEYCODES.get(str(name).strip().lower())


def ydotool_available():
    return shutil.which("ydotool") is not None


def ydotool_key(code, down, dry=False):
    action = f"{code}:{1 if down else 0}"
    if dry:
        logger.debug(f"[DRY] ydotool key {action}")
        return True
    try:
        subprocess.run(["ydotool", "key", action], check=True, capture_output=True, timeout=2)
        return True
    except Exception as e:
        logger.error(f"ydotool key injection failed: {e}")
        return False


# Android KeyEvent keycodes (frameworks/base/core/java/android/view/KeyEvent.java), for
# triggering PTT inside Android-in-a-container targets (docker-android/budtmo, HQarroum's
# docker-android, and Waydroid) over ADB, where there is no host window for pynput/ydotool
# to inject into at all.
ANDROID_ADB_KEYCODES = {
    "f1": 131, "f2": 132, "f3": 133, "f4": 134, "f5": 135, "f6": 136,
    "f7": 137, "f8": 138, "f9": 139, "f10": 140, "f11": 141, "f12": 142,
    "esc": 111, "escape": 111,
    "space": 62,
    "enter": 66, "return": 66,
    "tab": 61,
    "shift": 59, "ctrl": 113, "alt": 57, "cmd": 117, "win": 117,
    "a": 29, "b": 30, "c": 31, "d": 32, "e": 33, "f": 34, "g": 35,
    "h": 36, "i": 37, "j": 38, "k": 39, "l": 40, "m": 41, "n": 42,
    "o": 43, "p": 44, "q": 45, "r": 46, "s": 47, "t": 48, "u": 49,
    "v": 50, "w": 51, "x": 52, "y": 53, "z": 54,
    "0": 7, "1": 8, "2": 9, "3": 10, "4": 11, "5": 12, "6": 13, "7": 14, "8": 15, "9": 16,
}


def adb_keycode(name):
    if not name:
        return None
    return ANDROID_ADB_KEYCODES.get(str(name).strip().lower())


def adb_available():
    return shutil.which("adb") is not None


def adb_ensure_connected(serial, dry=False):
    if not serial:
        return False
    if dry:
        logger.debug(f"[DRY] adb connect {serial}")
        return True
    try:
        result = subprocess.run(
            ["adb", "connect", serial], capture_output=True, text=True, timeout=5
        )
        output = (result.stdout or "") + (result.stderr or "")
        ok = "connected to" in output.lower() or "already connected" in output.lower()
        if not ok:
            logger.error(f"adb connect {serial} failed: {output.strip()}")
        return ok
    except Exception as e:
        logger.error(f"adb connect {serial} failed: {e}")
        return False


def adb_key_tap(serial, code, dry=False):
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += ["shell", "input", "keyevent", str(code)]

    if dry:
        logger.debug(f"[DRY] {' '.join(cmd)}")
        return True
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=5)
        return True
    except Exception as e:
        logger.error(f"adb keyevent injection failed: {e}")
        return False


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

    # injection_mode controls how the PTT hotkey reaches the Zello target:
    #   auto    - pynput normally; ydotool automatically on a detected Wayland session
    #   pynput  - always use host keyboard injection (X11/macOS/Windows)
    #   ydotool - always use ydotool (Linux uinput injection)
    #   adb     - send an ADB `input keyevent` tap into an Android target (docker-android,
    #             Waydroid-with-adb, or any adb-reachable emulator/device). This is
    #             edge-triggered, not press-and-hold: set Zello's PTT hotkey to TOGGLE mode.
    "injection_mode": "auto",
    "adb_serial": None,

    # Seconds to wait for the radio's USB serial/HID device to enumerate before giving up.
    # Matters on headless boot (e.g. a Pi powering on alongside its USB radio interface),
    # where udev can lag a systemd service start by a few seconds. 0 disables waiting.
    "serial_wait_timeout": 30,

    "cm108": {
        "vendor_id": 0x0D8C,
        "product_id": None,
        "gpio_mask": 0x04,
        "active_low": False
    },

    # radio_type: "asterisk" connects to a local or remote Asterisk instance (app_rpt)
    # over the USRP protocol instead of a physical radio interface. No serial/USB
    # device is used for this backend.
    "asterisk": {
        "host": "127.0.0.1",
        "port": 32001,
        "local_port": 0
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


def wait_until(check_fn, timeout, poll_interval=1.0, waiting_message=None):
    """Poll check_fn() until it returns a truthy value or timeout elapses.

    On a headless boot (e.g. a Pi powering up alongside its USB radio interface),
    the interface's udev/USB enumeration can lag the service start by a few
    seconds. Retrying here avoids a hard failure -> full systemd restart cycle
    for what is normally just a brief startup race.
    """
    deadline = time.monotonic() + timeout if timeout > 0 else time.monotonic()
    logged = False
    while True:
        result = check_fn()
        if result:
            return result
        if time.monotonic() >= deadline:
            return result
        if waiting_message and not logged:
            logger.info(waiting_message)
            logged = True
        time.sleep(poll_interval)


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
    except Exception as e:
        print(f"Failed to query audio devices: {e}")
        return

    if not devices:
        print("No audio devices found.")
        print(
            "On Linux (e.g. Raspberry Pi OS), this usually means PortAudio can't see any "
            "PipeWire/ALSA/Pulse devices. Try installing 'pipewire-pulse'/'pipewire-alsa' "
            "(or 'pulseaudio'), confirm 'aplay -l' lists a device, then retry."
        )
        return

    for i, dev in enumerate(devices):
        name = dev.get("name")
        role = _audio_role_label(dev)
        print(f"[{i}] {name} ({role})")


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
    # True for backends that carry audio themselves (e.g. over a network socket),
    # rather than through the local sd.Stream device pair like the hardware backends.
    transports_audio = False

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

    def __init__(self, serial_port, baud, ptt_output="dtr", active_low=False, ignore_initial_state=True):
        self.serial_port = serial_port
        self.baud = baud
        self.ptt_output = (ptt_output or "dtr").lower()
        self.active_low = bool(active_low)
        self.ignore_initial_state = bool(ignore_initial_state)
        self.ser = None

    def open(self):
        self.ser = serial.Serial(self.serial_port, baudrate=self.baud, timeout=0)
        if self.ignore_initial_state:
            try:
                logger.info("Ignoring initial PTT state: forcing DTR/RTS off after opening serial port.")
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

    def __init__(self, vendor_id=0x0D8C, product_id=None, gpio_mask=0x04, active_low=False, ignore_initial_state=True):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.gpio_mask = int(gpio_mask) & 0xFF
        self.active_low = bool(active_low)
        self.ignore_initial_state = bool(ignore_initial_state)
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

        if self.ignore_initial_state:
            try:
                logger.info("Ignoring initial PTT state: forcing CM108 GPIO off after opening device.")
                self._write_gpio(False)
                time.sleep(0.05)
            except Exception:
                pass

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


# USRP is the UDP audio+PTT wire format used by Asterisk's app_rpt (chan_usrp/simpleusb)
# to let an external program act as a "radio" node without being a compiled Asterisk
# channel driver. 32-byte header (big-endian) + 160 samples (20ms) of 16-bit signed
# linear PCM audio at 8000 Hz, mono, when type == USRP_TYPE_VOICE.
USRP_TYPE_VOICE = 0
USRP_TYPE_DTMF = 1
USRP_TYPE_TEXT = 2
USRP_TYPE_PING = 3
USRP_SAMPLE_RATE = 8000
USRP_FRAME_SAMPLES = 160  # 20ms @ 8kHz
USRP_HEADER_FMT = ">4sIIIIIII"
USRP_HEADER_LEN = struct.calcsize(USRP_HEADER_FMT)


def pcm16_frame(mono_float, target_len):
    clipped = np.clip(mono_float, -1.0, 1.0)
    ints = (clipped * 32767.0).astype("<i2")
    if ints.size < target_len:
        ints = np.pad(ints, (0, target_len - ints.size))
    elif ints.size > target_len:
        ints = ints[:target_len]
    return ints


def fit_frame(mono_float, target_len):
    if mono_float.size < target_len:
        mono_float = np.pad(mono_float, (0, target_len - mono_float.size))
    elif mono_float.size > target_len:
        mono_float = mono_float[:target_len]
    return mono_float.reshape(-1, 1).astype(np.float32)


def resample_linear(samples, src_rate, dst_rate):
    if samples.size == 0 or src_rate == dst_rate:
        return samples.astype(np.float32)
    duration = samples.shape[0] / float(src_rate)
    dst_len = int(round(duration * dst_rate))
    if dst_len <= 0:
        return np.zeros(0, dtype=np.float32)
    src_idx = np.linspace(0, samples.shape[0] - 1, num=dst_len)
    return np.interp(src_idx, np.arange(samples.shape[0]), samples).astype(np.float32)


class AsteriskRadio(RadioInterfaceBase):
    """Connects to a local or remote Asterisk instance (app_rpt) over the USRP
    protocol, in place of a physical radio interface. Unlike the hardware backends,
    this one carries audio itself over the network rather than through a local
    sd.Stream device pair - see transports_audio."""

    name = "asterisk"
    transports_audio = True

    def __init__(self, host, port, local_port=0):
        self.host = host
        self.port = int(port)
        self.local_port = int(local_port or 0)
        self.sock = None
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.rx_queue = queue.Queue(maxsize=50)
        self.rx_thread = None
        self.stop_flag = threading.Event()

    def open(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.local_port))
        self.sock.settimeout(1.0)
        self.stop_flag.clear()
        self.rx_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.rx_thread.start()
        bound_port = self.sock.getsockname()[1]
        logger.info(
            f"Asterisk USRP backend: sending to {self.host}:{self.port}, "
            f"listening on 0.0.0.0:{bound_port}"
        )

    def _recv_loop(self):
        while not self.stop_flag.is_set():
            try:
                data, _ = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break

            if len(data) < USRP_HEADER_LEN:
                continue
            try:
                eye, seq, memory, keyup, talkgroup, ptype, mpxid, reserved = struct.unpack(
                    USRP_HEADER_FMT, data[:USRP_HEADER_LEN]
                )
            except struct.error:
                continue
            if eye != b"USRP" or ptype != USRP_TYPE_VOICE or np is None:
                continue

            payload = data[USRP_HEADER_LEN:USRP_HEADER_LEN + USRP_FRAME_SAMPLES * 2]
            if not payload:
                continue
            ints = np.frombuffer(payload, dtype="<i2")
            floats = ints.astype(np.float32) / 32768.0
            item = (floats, bool(keyup))

            try:
                self.rx_queue.put_nowait(item)
            except queue.Full:
                try:
                    self.rx_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.rx_queue.put_nowait(item)
                except queue.Full:
                    pass

    def recv_audio_nowait(self):
        try:
            return self.rx_queue.get_nowait()
        except queue.Empty:
            return None

    def send_audio(self, pcm16_array, keyup, dry=False):
        if dry:
            return
        if self.sock is None:
            return
        with self.seq_lock:
            self.seq += 1
            seq = self.seq
        header = struct.pack(
            USRP_HEADER_FMT, b"USRP", seq, 0, 1 if keyup else 0, 0, USRP_TYPE_VOICE, 0, 0
        )
        try:
            self.sock.sendto(header + pcm16_array.tobytes(), (self.host, self.port))
        except Exception as e:
            logger.error(f"USRP send failed: {e}")

    def ptt_on(self, dry=False):
        # Outbound keyup is driven per-frame from audio_callback (see main()), not
        # here - this exists so PTTController's hotkey-injection plumbing still has
        # a backend method to call when relaying an Asterisk-side keyup into Zello.
        if not dry:
            logger.debug("Asterisk backend: relayed PTT DOWN (from remote keyup)")

    def ptt_off(self, dry=False):
        if not dry:
            logger.debug("Asterisk backend: relayed PTT UP (from remote keyup)")

    def close(self):
        self.stop_flag.set()
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        if self.rx_thread is not None:
            self.rx_thread.join(timeout=2.0)
            self.rx_thread = None


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
    ignore_initial_state = bool(
        getattr(args, "ignore_initial_ptt_state", False) or cfg.get("ignore_initial_ptt_state", True)
    )
    serial_wait_timeout = float(
        args.serial_wait_timeout
        if getattr(args, "serial_wait_timeout", None) is not None
        else cfg.get("serial_wait_timeout", 30)
    )

    if radio_type == "cm108":
        if usb is None:
            logger.error("pyusb not installed. Install with: pip install pyusb")
            sys.exit(2)

        cm_cfg = cfg.get("cm108", {})
        vendor_id = int(cm_cfg.get("vendor_id", 0x0D8C))
        product_id = cm_cfg.get("product_id", None)
        gpio_mask = int(cm_cfg.get("gpio_mask", 0x04))
        active_low = bool(cm_cfg.get("active_low", False))

        def _find_cm108():
            kwargs = {"idVendor": vendor_id}
            if product_id is not None:
                kwargs["idProduct"] = product_id
            try:
                return usb.core.find(**kwargs) is not None
            except Exception:
                return False

        found = wait_until(
            _find_cm108,
            serial_wait_timeout,
            waiting_message=(
                f"Waiting up to {serial_wait_timeout:.0f}s for CM108/CM119 device "
                f"(vendor=0x{vendor_id:04x}) to enumerate..."
            ),
        )
        if not found:
            logger.error(
                f"CM108/CM119 device not found (vendor=0x{vendor_id:04x}) after "
                f"waiting {serial_wait_timeout:.0f}s."
            )
            sys.exit(2)

        return CM108Radio(
            vendor_id=vendor_id,
            product_id=product_id,
            gpio_mask=gpio_mask,
            active_low=active_low,
            ignore_initial_state=ignore_initial_state,
        )

    if radio_type == "asterisk":
        if np is None:
            logger.error("numpy is required for the Asterisk USRP backend.")
            sys.exit(2)
        ast_cfg = cfg.get("asterisk", {})
        host = args.asterisk_host or ast_cfg.get("host") or "127.0.0.1"
        port = int(args.asterisk_port if args.asterisk_port is not None else ast_cfg.get("port", 32001))
        local_port = int(
            args.asterisk_local_port
            if args.asterisk_local_port is not None
            else ast_cfg.get("local_port", 0)
        )
        return AsteriskRadio(host=host, port=port, local_port=local_port)

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
        detected = wait_until(
            lambda: autodetect_serial(cfg.get("serial_autodetect_hints", [])),
            serial_wait_timeout,
            waiting_message=(
                f"No serial device detected yet; waiting up to {serial_wait_timeout:.0f}s "
                "for one to appear..."
            ),
        )
        if detected:
            serial_port = detected
            logger.info(f"Auto-detected serial port: {serial_port}")
        else:
            logger.error(
                f"No serial port specified and auto-detect found none after waiting "
                f"{serial_wait_timeout:.0f}s."
            )
            sys.exit(2)
    elif serial_port.startswith(("/dev/", "/tmp/")):
        exists = wait_until(
            lambda: os.path.exists(serial_port),
            serial_wait_timeout,
            waiting_message=(
                f"Waiting up to {serial_wait_timeout:.0f}s for serial device "
                f"{serial_port} to appear..."
            ),
        )
        if not exists:
            logger.error(
                f"Serial device {serial_port} did not appear within {serial_wait_timeout:.0f}s."
            )
            sys.exit(2)

    baud = args.baud if args.baud is not None else int(cfg.get("baud", 9600))

    return DigiRigRadio(
        serial_port=serial_port,
        baud=baud,
        ptt_output=ptt_output,
        active_low=ptt_active_low,
        ignore_initial_state=ignore_initial_state,
    )


class PTTController:
    def __init__(
        self,
        backend,
        hotkey=None,
        hotkey_enabled=False,
        dry_run=False,
        ydotool_code=None,
        adb_code=None,
        adb_serial=None,
    ):
        self.backend = backend
        self.hotkey = hotkey
        self.hotkey_enabled = hotkey_enabled
        self.dry_run = dry_run
        self.ydotool_code = ydotool_code
        self.adb_code = adb_code
        self.adb_serial = adb_serial
        self.is_down = False
        self.lock = threading.Lock()

    def _inject_key(self, down):
        if self.adb_code is not None:
            # ADB `input keyevent` is a discrete tap, not press-and-hold: only fire on the
            # down edge and rely on Zello's TOGGLE hotkey mode, not HOLD.
            if down:
                adb_key_tap(self.adb_serial, self.adb_code, dry=self.dry_run)
            return
        if self.ydotool_code is not None:
            ydotool_key(self.ydotool_code, down, dry=self.dry_run)
        elif self.hotkey is not None:
            if down:
                press_key(self.hotkey, dry=self.dry_run)
            else:
                release_key(self.hotkey, dry=self.dry_run)

    def down(self, source="unknown"):
        with self.lock:
            if self.is_down:
                return
            self.is_down = True
            logger.info(f"PTT DOWN ({source})")

            if self.hotkey_enabled:
                logger.info("PTT DOWN -> adb toggle tap" if self.adb_code is not None else "PTT DOWN -> key down")
                self._inject_key(True)

            self.backend.ptt_on(dry=self.dry_run)

    def up(self, source="unknown"):
        with self.lock:
            if not self.is_down:
                return
            self.is_down = False
            logger.info(f"PTT UP ({source})")

            if self.hotkey_enabled:
                if self.adb_code is None:
                    logger.info("PTT UP -> key up")
                self._inject_key(False)

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


def sd_notify(message):
    """Best-effort systemd readiness/watchdog notification (sd_notify(3) protocol).

    No-ops entirely when not running under systemd (NOTIFY_SOCKET unset) and adds no
    dependency — this is a plain AF_UNIX datagram, not the `sdnotify` PyPI package.
    Used so `Type=notify` + `WatchdogSec=` in the systemd unit can detect a *hung*
    process (audio thread deadlocked, no watchdog pings) and restart it, which a plain
    `Restart=on-failure` cannot: that only fires on the process actually exiting.
    """
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.connect(addr)
            sock.sendall(message.encode())
        finally:
            sock.close()
    except Exception:
        pass


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

    parser = argparse.ArgumentParser(prog="zpttlink", description="ZPTTLink 3.0 Zello/radio/Asterisk bridge")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE)
    parser.add_argument("--key", help="Hotkey to send to Zello")
    parser.add_argument("--serial", help="Serial port override")
    parser.add_argument(
        "--serial-wait-timeout",
        type=float,
        default=None,
        help="Seconds to wait for the radio's USB device to enumerate before giving up "
        "(default 30; helps on headless boot where udev lags service start). 0 disables waiting.",
    )
    parser.add_argument("--baud", type=int, default=None)
    parser.add_argument(
        "--radio-type",
        choices=["auto", "cm108", "digirig", "signalink", "asterisk"],
        default=None,
    )
    parser.add_argument("--ptt-output", choices=["none", "dtr", "rts"], default=None)
    parser.add_argument("--asterisk-host", default=None, help="Asterisk USRP peer host/IP")
    parser.add_argument("--asterisk-port", type=int, default=None, help="Asterisk USRP peer port")
    parser.add_argument(
        "--asterisk-local-port",
        type=int,
        default=None,
        help="Local UDP port to bind for the Asterisk USRP backend (0 = OS-assigned)",
    )
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

    parser.add_argument(
        "--injection-mode",
        choices=["auto", "pynput", "ydotool", "adb"],
        default=None,
        help="How the hotkey reaches the Zello target. 'adb' targets Android-in-a-container "
        "(docker-android, Waydroid-with-adb) over ADB and requires --adb-serial.",
    )
    parser.add_argument(
        "--adb-serial",
        default=None,
        help="ADB target for --injection-mode adb, e.g. 127.0.0.1:5555",
    )

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

    force_serial_ptt = bool(args.force_serial_ptt or cfg.get("force_serial_ptt", False))
    hotkey_enabled = not (args.no_hotkey or cfg.get("disable_hotkey", False))
    if force_serial_ptt:
        hotkey_enabled = False

    hotkey_obj = None
    use_ydotool = False
    ydotool_code = None
    adb_code = None
    adb_serial_value = None

    if hotkey_enabled:
        injection_mode = str(args.injection_mode or cfg.get("injection_mode") or "auto").lower()
        is_wayland = platform.system() == "Linux" and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

        if injection_mode == "adb":
            adb_serial_value = args.adb_serial or cfg.get("adb_serial")
            if not adb_available():
                logger.error(
                    "injection_mode=adb but 'adb' was not found on PATH. "
                    "Install Android platform-tools."
                )
                sys.exit(10)
            if not adb_serial_value:
                logger.error(
                    "injection_mode=adb requires --adb-serial or config 'adb_serial' "
                    "(e.g. 127.0.0.1:5555)."
                )
                sys.exit(10)
            adb_code = adb_keycode(hotkey_name)
            if adb_code is None:
                logger.error(f"No ADB keycode mapping for hotkey '{hotkey_name}'.")
                sys.exit(10)
            if not adb_ensure_connected(adb_serial_value, dry=args.dry_run):
                logger.error(
                    f"Could not connect to ADB target {adb_serial_value}. Is the "
                    "container/emulator running and its ADB port reachable?"
                )
                sys.exit(10)
            logger.warning(
                "ADB PTT injection is edge-triggered (a single tap), not press-and-hold. "
                "Set Zello's PTT hotkey mode to TOGGLE (not Hold), or PTT will only ever "
                "start and never stop."
            )
            logger.info(f"ADB PTT target: {adb_serial_value} ({hotkey_name} -> keycode {adb_code})")

        elif injection_mode == "ydotool":
            candidate_code = ydotool_keycode(hotkey_name)
            if not ydotool_available() or candidate_code is None:
                logger.error(
                    "injection_mode=ydotool but ydotool is unavailable, or the hotkey has "
                    "no ydotool keycode mapping."
                )
                sys.exit(10)
            use_ydotool = True
            ydotool_code = candidate_code
            logger.info(f"Using ydotool for key injection ({hotkey_name} -> keycode {ydotool_code}).")

        elif injection_mode == "auto" and is_wayland:
            candidate_code = ydotool_keycode(hotkey_name)
            if ydotool_available() and candidate_code is not None:
                use_ydotool = True
                ydotool_code = candidate_code
                logger.info(
                    f"Wayland session detected; using ydotool for key injection "
                    f"({hotkey_name} -> keycode {ydotool_code})."
                )
            else:
                logger.warning(
                    "Wayland session detected and ydotool fallback is unavailable "
                    "(install ydotool, run 'sudo systemctl start ydotoold', or switch to "
                    "serial/CM108 PTT with --force-serial-ptt)."
                )

        if adb_code is None and not use_ydotool:
            if Controller is None:
                logger.error(
                    "pynput is not available for keyboard injection.\n"
                    "Install pynput, pass --no-hotkey / --force-serial-ptt to rely on serial "
                    "PTT only, or use --injection-mode ydotool/adb."
                )
                sys.exit(9)
            hotkey_obj = parse_hotkey(hotkey_name)
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
        ydotool_code=ydotool_code,
        adb_code=adb_code,
        adb_serial=adb_serial_value,
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

    usrp_local_keyed = [False]
    usrp_remote_keyed = [False]

    if backend.transports_audio:
        logger.info(
            f"Asterisk USRP mode: local audio keys Asterisk directly; incoming Asterisk "
            f"keyup relays into Zello via {'hotkey injection' if hotkey_enabled else 'PTT UP/DOWN log only (hotkey injection disabled!)'}."
        )
        if not hotkey_enabled:
            logger.warning(
                "hotkey_enabled is False with radio_type=asterisk: audio arriving from "
                "Asterisk will be written into Zello's mic input, but Zello won't be told "
                "to transmit it unless Zello's own VOX is enabled. Set force_serial_ptt: "
                "false and configure injection_mode to relay it properly."
            )

    def audio_callback(indata, outdata, frames, time_info, status):
        if status:
            logger.warning(f"TX callback status: {status}")

        level = rms_level(indata)
        maybe_log_level(level, vox_log_levels)

        if backend.transports_audio:
            # Outbound: local Zello audio -> Asterisk. Local VOX (reusing `gate`)
            # decides the outbound keyup flag; no hotkey injection needed here since
            # Zello is already producing this audio on its own.
            action = gate.process(level)
            if action == "start":
                usrp_local_keyed[0] = True
                logger.info("USRP TX keyup -> ON (local VOX)")
            elif action == "stop":
                usrp_local_keyed[0] = False
                logger.info("USRP TX keyup -> OFF (local VOX)")

            mono_in = np.asarray(indata, dtype=np.float32).reshape(-1)
            mono_8k = resample_linear(mono_in, samplerate, USRP_SAMPLE_RATE)
            pcm16 = pcm16_frame(mono_8k, USRP_FRAME_SAMPLES)
            backend.send_audio(pcm16, keyup=usrp_local_keyed[0], dry=args.dry_run)

            # Inbound: Asterisk -> Zello mic input. The remote keyup edge drives
            # ptt.down()/up() so hotkey injection actually relays it into Zello.
            rx = backend.recv_audio_nowait()
            if rx is not None:
                rx_samples, rx_keyup = rx
                if rx_keyup and not usrp_remote_keyed[0]:
                    usrp_remote_keyed[0] = True
                    ptt.down(source="asterisk-rx")
                elif not rx_keyup and usrp_remote_keyed[0]:
                    usrp_remote_keyed[0] = False
                    ptt.up(source="asterisk-rx")
                up = resample_linear(rx_samples, USRP_SAMPLE_RATE, samplerate)
                outdata[:] = fit_frame(up, frames)
            else:
                zero_out(outdata)
            return

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

    stream_kwargs = dict(
        device=(input_index, output_index),
        samplerate=samplerate,
        channels=1,
        dtype="float32",
        callback=audio_callback,
    )
    if backend.transports_audio:
        # Align each callback tick with one 20ms USRP frame.
        stream_kwargs["blocksize"] = int(round(samplerate * 0.02))

    try:
        audio_stream = sd.Stream(**stream_kwargs)
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
    logger.info("ZPTTLink 3.0 bridge is running successfully! (Ctrl+C to exit)")
    sd_notify("READY=1")

    exit_code = 0
    watchdog_interval = 10.0
    last_watchdog = time.monotonic()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)

            if audio_stream is not None and not audio_stream.active:
                logger.error(
                    "Audio stream is no longer active (device disconnected or errored); "
                    "exiting so the service manager can restart."
                )
                exit_code = 13
                break

            now = time.monotonic()
            if now - last_watchdog >= watchdog_interval:
                sd_notify("WATCHDOG=1")
                last_watchdog = now
    finally:
        sd_notify("STOPPING=1")

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

    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()