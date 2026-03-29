from __future__ import annotations

import io
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional

import sounddevice as sd
from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from .main import DEFAULT_CONFIG, list_audio_devices, list_serial_ports, load_config
except ImportError:
    from main import DEFAULT_CONFIG, list_audio_devices, list_serial_ports, load_config


APP_TITLE = "ZPTTLink 2.0.0"
CONFIG_PATH = Path("config.json")
BASE_DIR = Path(__file__).resolve().parent.parent

ASSET_ICON_CANDIDATES = [
    BASE_DIR / "assets" / "logo.png",
    BASE_DIR / "assets" / "icons" / "zpttlink.png",
    BASE_DIR / "assets" / "icons" / "zpttlink.ico",
    BASE_DIR / "assets" / "icons" / "zpttlink.icns",
]


def detect_bluestacks_mac() -> bool:
    candidates = [
        Path("/Applications/BlueStacks.app"),
        Path.home() / "Applications" / "BlueStacks.app",
    ]
    if any(p.exists() for p in candidates):
        return True

    try:
        out = subprocess.run(
            ["pgrep", "-fl", "BlueStacks"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except Exception:
        return False


def detect_waydroid_linux() -> bool:
    if platform.system() != "Linux":
        return False
    if os.environ.get("WAYDROID_SESSION"):
        return True
    return shutil.which("waydroid") is not None


def detect_android_runtime() -> str:
    system = platform.system()

    if system == "Darwin":
        return "BlueStacks" if detect_bluestacks_mac() else "none detected"

    if system == "Linux":
        return "Waydroid" if detect_waydroid_linux() else "none detected"

    if system == "Windows":
        return "none detected"

    return "n/a"


def detect_audio_backend() -> str:
    system = platform.system()

    if system == "Darwin":
        return "CoreAudio"

    if system == "Windows":
        return "WASAPI/MME"

    if system == "Linux":
        if os.environ.get("PIPEWIRE_RUNTIME_DIR") or shutil.which("pw-cli") or shutil.which("pipewire"):
            return "PipeWire"
        if os.environ.get("PULSE_SERVER") or shutil.which("pactl") or shutil.which("pulseaudio"):
            return "PulseAudio"
        if shutil.which("aplay") or Path("/proc/asound").exists():
            return "ALSA"
        return "Linux audio (unknown)"

    return "n/a"


def format_audio_device_label(index: int, dev: dict) -> str:
    name = str(dev.get("name", f"Device {index}")).strip()
    in_ch = int(dev.get("max_input_channels", 0) or 0)
    out_ch = int(dev.get("max_output_channels", 0) or 0)

    if in_ch > 0 and out_ch > 0:
        role = "Input+Output / RX+TX"
    elif in_ch > 0:
        role = "Input / RX"
    elif out_ch > 0:
        role = "Output / TX"
    else:
        role = "No I/O"

    return f"[{index}] {name} ({role})"


class QtLogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        self.callback(msg)


class IndicatorDot(QLabel):
    COLORS = {
        "idle": "#7a7a7a",
        "armed": "#1e88e5",
        "tx": "#d32f2f",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.set_state("idle")

    def set_state(self, state: str):
        color = self.COLORS.get(state, self.COLORS["idle"])
        self.setStyleSheet(
            f"border-radius: 11px; background: {color}; border: 1px solid #444;"
        )


class PTTPushButton(QPushButton):
    def __init__(self, on_down, on_up, parent=None):
        super().__init__("PTT", parent)
        self._on_down = on_down
        self._on_up = on_up
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            """
            QPushButton {
                font-size: 22px;
                font-weight: 700;
                border-radius: 18px;
                border: 2px solid #555;
                background: #2b2b2b;
                color: white;
                padding: 18px;
            }
            QPushButton:pressed {
                background: #b71c1c;
                border: 2px solid #ef5350;
            }
            """
        )

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self._on_down()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._on_up()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1240, 860)
        self._load_icon()

        self.cfg = load_config(str(CONFIG_PATH))
        self.proc: Optional[QProcess] = None
        self.current_ptt_down = False
        self.ignore_next_initial_ptt_state = False
        self.log_handler = None

        self.serial_refresh_timer = QTimer(self)
        self.serial_refresh_timer.setInterval(2500)
        self.serial_refresh_timer.timeout.connect(self.refresh_serial_devices)

        self._build_ui()
        self._attach_gui_logger()
        self.refresh_serial_devices()
        self.refresh_audio_devices()
        self.serial_refresh_timer.start()
        self.update_env_status()
        self._apply_platform_defaults()
        self.log("GUI ready.")

    def _load_icon(self):
        for candidate in ASSET_ICON_CANDIDATES:
            if candidate.exists():
                self.setWindowIcon(QIcon(str(candidate)))
                break

    def _attach_gui_logger(self):
        root = logging.getLogger("zpttlink")
        if not root.handlers:
            root = logging.getLogger()
        self.log_handler = QtLogHandler(self.log)
        self.log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(self.log_handler)

    def closeEvent(self, event):
        try:
            self.stop_runtime()
        finally:
            if self.log_handler:
                logging.getLogger().removeHandler(self.log_handler)
        super().closeEvent(event)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QGridLayout()
        root.addLayout(top)

        top.addWidget(self._build_connection_group(), 0, 0)
        top.addWidget(self._build_audio_group(), 0, 1)
        top.addWidget(self._build_runtime_group(), 1, 0)
        top.addWidget(self._build_status_group(), 1, 1)

        controls = QHBoxLayout()
        self.btn_save = QPushButton("Save Config")
        self.btn_save.clicked.connect(self.save_config)
        self.btn_test = QPushButton("Test Serial PTT")
        self.btn_test.clicked.connect(self.test_serial_ptt)
        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.start_runtime)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop_runtime)
        self.btn_stop.setEnabled(False)
        self.btn_browse_icon = QPushButton("Set Icon…")
        self.btn_browse_icon.clicked.connect(self.choose_icon)

        for btn in [self.btn_save, self.btn_test, self.btn_start, self.btn_stop, self.btn_browse_icon]:
            controls.addWidget(btn)
        root.addLayout(controls)

        self.ptt_button = PTTPushButton(self.manual_ptt_down, self.manual_ptt_up)
        root.addWidget(self.ptt_button)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        root.addWidget(self.log_view, 1)

    def _build_connection_group(self):
        group = QGroupBox("Connection")
        layout = QFormLayout(group)

        serial_row = QHBoxLayout()
        self.serial_combo = QComboBox()
        self.btn_refresh_serial = QPushButton("Refresh")
        self.btn_refresh_serial.clicked.connect(self.refresh_serial_devices)
        serial_row.addWidget(self.serial_combo, 1)
        serial_row.addWidget(self.btn_refresh_serial)
        layout.addRow("Serial Port", self._wrap(serial_row))

        self.hotkey_edit = QLineEdit(self.cfg.get("ptt_hotkey", "F9"))
        layout.addRow("Hotkey", self.hotkey_edit)

        self.ptt_mode_combo = QComboBox()
        self.ptt_mode_combo.addItems(["none", "dtr", "rts"])
        self.ptt_mode_combo.setCurrentText(self.cfg.get("ptt_output", "rts"))
        self.ptt_mode_combo.currentTextChanged.connect(self._on_ptt_mode_changed)
        layout.addRow("PTT Output", self.ptt_mode_combo)

        self.chk_ignore_initial_ptt = QCheckBox("Ignore initial PTT state on serial open")
        self.chk_ignore_initial_ptt.setChecked(
            bool(self.cfg.get("ignore_initial_ptt_state", True))
        )
        layout.addRow("", self.chk_ignore_initial_ptt)

        return group

    def _build_audio_group(self):
        group = QGroupBox("Audio")
        layout = QFormLayout(group)

        self.audio_in_combo = QComboBox()
        self.audio_out_combo = QComboBox()
        self.btn_refresh_audio = QPushButton("Refresh Audio")
        self.btn_refresh_audio.clicked.connect(self.refresh_audio_devices)

        layout.addRow("Input", self.audio_in_combo)
        layout.addRow("Output", self.audio_out_combo)
        layout.addRow("", self.btn_refresh_audio)
        return group

    def _build_runtime_group(self):
        group = QGroupBox("Runtime")
        layout = QVBoxLayout(group)

        self.chk_no_hotkey = QCheckBox("Disable hotkey injection")
        self.chk_no_hotkey.setChecked(bool(self.cfg.get("no_hotkey", False)))

        self.chk_dry_run = QCheckBox("Dry run")
        self.chk_dry_run.setChecked(bool(self.cfg.get("dry_run", False)))

        self.chk_force_serial_ptt = QCheckBox("Force serial PTT (prefer DTR/RTS over key injection)")
        self.chk_force_serial_ptt.setChecked(bool(self.cfg.get("force_serial_ptt", True)))

        vox_group = QGroupBox("VOX")
        vox_form = QFormLayout(vox_group)

        vox_cfg = self.cfg.get("vox", {})

        self.chk_vox_enabled = QCheckBox("Enable VOX")
        self.chk_vox_enabled.setChecked(bool(vox_cfg.get("enabled", False)))

        self.spin_vox_threshold = QDoubleSpinBox()
        self.spin_vox_threshold.setRange(0.001, 1.000)
        self.spin_vox_threshold.setDecimals(3)
        self.spin_vox_threshold.setSingleStep(0.005)
        self.spin_vox_threshold.setValue(float(vox_cfg.get("threshold", 0.020)))

        self.spin_vox_attack = QSpinBox()
        self.spin_vox_attack.setRange(0, 5000)
        self.spin_vox_attack.setValue(int(vox_cfg.get("attack_ms", 40)))

        self.spin_vox_release = QSpinBox()
        self.spin_vox_release.setRange(0, 5000)
        self.spin_vox_release.setValue(int(vox_cfg.get("release_ms", 120)))

        self.spin_vox_hang = QSpinBox()
        self.spin_vox_hang.setRange(0, 5000)
        self.spin_vox_hang.setValue(int(vox_cfg.get("hang_ms", 300)))

        vox_form.addRow("", self.chk_vox_enabled)
        vox_form.addRow("Threshold", self.spin_vox_threshold)
        vox_form.addRow("Attack (ms)", self.spin_vox_attack)
        vox_form.addRow("Release (ms)", self.spin_vox_release)
        vox_form.addRow("Hang (ms)", self.spin_vox_hang)

        layout.addWidget(self.chk_no_hotkey)
        layout.addWidget(self.chk_dry_run)
        layout.addWidget(self.chk_force_serial_ptt)
        layout.addWidget(vox_group)
        layout.addStretch(1)
        return group

    def _build_status_group(self):
        group = QGroupBox("Status")
        layout = QFormLayout(group)

        self.indicator = IndicatorDot()
        self.lbl_ptt = QLabel("Idle")
        dot_row = QHBoxLayout()
        dot_row.addWidget(self.indicator)
        dot_row.addWidget(self.lbl_ptt)
        dot_row.addStretch(1)
        layout.addRow("PTT", self._wrap(dot_row))

        self.lbl_platform = QLabel("-")
        self.lbl_session = QLabel("-")
        self.lbl_android_runtime = QLabel("-")
        self.lbl_audio_backend = QLabel("-")
        self.lbl_helper = QLabel("-")

        layout.addRow("Platform", self.lbl_platform)
        layout.addRow("Session", self.lbl_session)
        layout.addRow("Android Runtime", self.lbl_android_runtime)
        layout.addRow("Audio Backend", self.lbl_audio_backend)
        layout.addRow("Helper", self.lbl_helper)
        return group

    def _wrap(self, layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    def _apply_platform_defaults(self):
        system = platform.system()
        ptt_mode = self.ptt_mode_combo.currentText()

        if ptt_mode in {"dtr", "rts"} and self.chk_force_serial_ptt.isChecked():
            self.chk_no_hotkey.setChecked(True)

        if system == "Linux":
            session = os.environ.get("XDG_SESSION_TYPE", "").lower()
            if session == "wayland" and ptt_mode in {"dtr", "rts"}:
                self.chk_no_hotkey.setChecked(True)

    def _on_ptt_mode_changed(self, value: str):
        if value in {"dtr", "rts"} and self.chk_force_serial_ptt.isChecked():
            self.chk_no_hotkey.setChecked(True)

    def log(self, message: str):
        self.log_view.appendPlainText(message)
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cursor)

    def update_env_status(self):
        system = platform.system()
        session = os.environ.get("XDG_SESSION_TYPE", "n/a")
        android_runtime = detect_android_runtime()
        audio_backend = detect_audio_backend()

        self.lbl_platform.setText(system)
        self.lbl_session.setText(session)
        self.lbl_android_runtime.setText(android_runtime)

        if system == "Linux":
            helper_ok = shutil.which("ydotool") is not None
            self.lbl_helper.setText("ydotool: Yes" if helper_ok else "ydotool: No")
        else:
            self.lbl_helper.setText("n/a")

        self.lbl_audio_backend.setText(audio_backend)
        self.set_indicator("armed", "Ready")

    def set_indicator(self, state: str, label: str):
        self.indicator.set_state(state)
        self.lbl_ptt.setText(label)

    def refresh_serial_devices(self):
        current = self.serial_combo.currentText()
        self.serial_combo.blockSignals(True)
        self.serial_combo.clear()
        ports = list_serial_ports()
        for p in ports:
            text = p.device
            if p.description and p.description != "n/a":
                text = f"{p.device} — {p.description}"
            self.serial_combo.addItem(text, p.device)
        self.serial_combo.blockSignals(False)

        target = self.cfg.get("com_port")
        selected = None
        for candidate in [current, target]:
            if not candidate:
                continue
            for i in range(self.serial_combo.count()):
                if self.serial_combo.itemData(i) == candidate or self.serial_combo.itemText(i).startswith(candidate):
                    selected = i
                    break
            if selected is not None:
                break
        if selected is not None:
            self.serial_combo.setCurrentIndex(selected)
        self.log("Serial devices refreshed.")

    def refresh_audio_devices(self):
        current_in_data = self.audio_in_combo.currentData()
        current_out_data = self.audio_out_combo.currentData()

        self.audio_in_combo.clear()
        self.audio_out_combo.clear()

        try:
            devices = sd.query_devices()
        except Exception as e:
            self.log(f"Audio refresh failed: {e}")
            return

        entries = []
        for idx, dev in enumerate(devices):
            label = format_audio_device_label(idx, dev)
            entries.append((idx, label))

        for dev_index, label in entries:
            self.audio_in_combo.addItem(label, dev_index)
            self.audio_out_combo.addItem(label, dev_index)

        self._restore_audio_combo(
            self.audio_in_combo,
            current_in_data,
            self.cfg.get("audio_input_index"),
            self.cfg.get("audio_input"),
        )
        self._restore_audio_combo(
            self.audio_out_combo,
            current_out_data,
            self.cfg.get("audio_output_index"),
            self.cfg.get("audio_output"),
        )

        self.log("Audio devices refreshed.")

    def _restore_audio_combo(self, combo: QComboBox, current_data, saved_index, saved_value):
        for preferred in [current_data, saved_index]:
            if preferred is None:
                continue
            for i in range(combo.count()):
                if combo.itemData(i) == preferred:
                    combo.setCurrentIndex(i)
                    return

        if saved_value:
            normalized = saved_value.strip()
            for i in range(combo.count()):
                text = combo.itemText(i)
                if text == normalized or normalized in text:
                    combo.setCurrentIndex(i)
                    return

    def choose_icon(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Icon", "", "Images (*.png *.ico *.icns)")
        if path:
            self.setWindowIcon(QIcon(path))
            self.log(f"Loaded icon: {path}")

    def config_payload(self):
        payload = DEFAULT_CONFIG.copy()
        payload.update(self.cfg)

        payload["com_port"] = self.serial_combo.currentData() or self.serial_combo.currentText().split(" — ", 1)[0]
        payload["audio_input"] = self.audio_in_combo.currentText()
        payload["audio_output"] = self.audio_out_combo.currentText()
        payload["audio_input_index"] = self.audio_in_combo.currentData()
        payload["audio_output_index"] = self.audio_out_combo.currentData()
        payload["ptt_hotkey"] = self.hotkey_edit.text().strip() or "F9"
        payload["ptt_output"] = self.ptt_mode_combo.currentText()
        payload["no_hotkey"] = self.chk_no_hotkey.isChecked()
        payload["disable_hotkey"] = self.chk_no_hotkey.isChecked()
        payload["dry_run"] = self.chk_dry_run.isChecked()
        payload["force_serial_ptt"] = self.chk_force_serial_ptt.isChecked()
        payload["ignore_initial_ptt_state"] = self.chk_ignore_initial_ptt.isChecked()

        payload["vox"] = {
            "enabled": self.chk_vox_enabled.isChecked(),
            "threshold": self.spin_vox_threshold.value(),
            "attack_ms": self.spin_vox_attack.value(),
            "release_ms": self.spin_vox_release.value(),
            "hang_ms": self.spin_vox_hang.value(),
        }

        return payload

    def save_config(self):
        payload = self.config_payload()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
            f.write("\n")
        self.cfg = payload
        self.log(f"Saved config to {CONFIG_PATH}")

    def _base_args(self):
        args = [
            "-m",
            "zpttlink",
            "--serial",
            self.serial_combo.currentData() or self.serial_combo.currentText().split(" — ", 1)[0],
        ]

        hotkey = self.hotkey_edit.text().strip()
        ptt_mode = self.ptt_mode_combo.currentText()

        if hotkey and not self.chk_no_hotkey.isChecked():
            args.extend(["--key", hotkey])

        if ptt_mode and ptt_mode != "none":
            args.extend(["--ptt-output", ptt_mode])

        if self.chk_no_hotkey.isChecked():
            args.append("--no-hotkey")

        if self.chk_dry_run.isChecked():
            args.append("--dry-run")

        vox_cfg = self.config_payload().get("vox", {})
        if vox_cfg.get("enabled", False):
            args.extend(["--vox"])
            args.extend(["--vox-threshold", str(vox_cfg["threshold"])])
            args.extend(["--vox-attack-ms", str(vox_cfg["attack_ms"])])
            args.extend(["--vox-release-ms", str(vox_cfg["release_ms"])])
            args.extend(["--vox-hang-ms", str(vox_cfg["hang_ms"])])

        if self.chk_ignore_initial_ptt.isChecked():
            args.append("--ignore-initial-ptt-state")

        if self.chk_force_serial_ptt.isChecked():
            args.append("--force-serial-ptt")

        if self.audio_in_combo.currentData() is not None:
            args.extend(["--audio-input-index", str(self.audio_in_combo.currentData())])

        if self.audio_out_combo.currentData() is not None:
            args.extend(["--audio-output-index", str(self.audio_out_combo.currentData())])

        return args

    def start_runtime(self):
        if self.proc:
            self.log("Runtime already running.")
            return

        self.save_config()
        self.ignore_next_initial_ptt_state = bool(self.chk_ignore_initial_ptt.isChecked())

        self.proc = QProcess(self)
        self.proc.setProgram(sys.executable)
        self.proc.setArguments(self._base_args())
        self.proc.readyReadStandardOutput.connect(self._read_stdout)
        self.proc.readyReadStandardError.connect(self._read_stderr)
        self.proc.finished.connect(self._proc_finished)
        self.proc.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.set_indicator("armed", "Running")
        self.log("Started runtime.")

    def stop_runtime(self):
        if not self.proc:
            return

        self.proc.terminate()
        if not self.proc.waitForFinished(1500):
            self.proc.kill()

        self.proc = None
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.current_ptt_down = False
        self.set_indicator("idle", "Stopped")
        self.log("Stopped runtime.")

    def _read_stdout(self):
        if not self.proc:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        for line in text.splitlines():
            self.log(line)
            self._parse_ptt_state(line)

    def _read_stderr(self):
        if not self.proc:
            return
        text = bytes(self.proc.readAllStandardError()).decode(errors="replace")
        for line in text.splitlines():
            self.log(line)
            self._parse_ptt_state(line)

    def _proc_finished(self):
        self.proc = None
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.current_ptt_down = False
        self.set_indicator("idle", "Stopped")

    def _parse_ptt_state(self, line: str):
        lower = line.lower()

        if self.ignore_next_initial_ptt_state:
            if "ptt up" in lower or "ptt down" in lower:
                self.ignore_next_initial_ptt_state = False
                self.log("Ignored initial PTT state report.")
                return

        if "ptt down" in lower:
            self.current_ptt_down = True
            self.set_indicator("tx", "TX active")
        elif "ptt up" in lower:
            self.current_ptt_down = False
            self.set_indicator("armed", "Ready")

    def test_serial_ptt(self):
        self.log("Testing serial PTT...")
        args = self._base_args() + ["--test-ptt"]
        proc = QProcess(self)
        proc.finished.connect(proc.deleteLater)
        proc.setProgram(sys.executable)
        proc.setArguments(args)
        proc.readyReadStandardOutput.connect(
            lambda: self.log(bytes(proc.readAllStandardOutput()).decode(errors="replace").strip())
        )
        proc.readyReadStandardError.connect(
            lambda: self.log(bytes(proc.readAllStandardError()).decode(errors="replace").strip())
        )
        proc.start()

    def manual_ptt_down(self):
        if self.current_ptt_down:
            return
        self.current_ptt_down = True
        self.set_indicator("tx", "TX active")
        self.log("Manual PTT DOWN")

    def manual_ptt_up(self):
        if not self.current_ptt_down:
            return
        self.current_ptt_down = False
        self.set_indicator("armed", "Ready")
        self.log("Manual PTT UP")


def launch_gui(argv=None):
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)

    for candidate in ASSET_ICON_CANDIDATES:
        if candidate.exists():
            app.setWindowIcon(QIcon(str(candidate)))
            break

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(launch_gui())
