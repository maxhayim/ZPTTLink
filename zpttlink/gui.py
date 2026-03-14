from __future__ import annotations

import io
import logging
import os
import platform
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .main import DEFAULT_CONFIG, list_audio_devices, list_serial_ports, load_config

APP_TITLE = "ZPTTLink 2.0.0"
CONFIG_PATH = Path("config.json")
ASSET_ICON_CANDIDATES = [
    Path("assets/icons/zpttlink.png"),
    Path("assets/icons/zpttlink.ico"),
    Path("assets/icons/zpttlink.icns"),
]


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
        self.resize(980, 720)
        self._load_icon()

        self.cfg = load_config(str(CONFIG_PATH))
        self.proc: Optional[QProcess] = None
        self.current_ptt_down = False
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
        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.start_runtime)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop_runtime)
        self.btn_stop.setEnabled(False)
        self.btn_test = QPushButton("Test Serial PTT")
        self.btn_test.clicked.connect(self.test_serial_ptt)
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
        self.ptt_mode_combo.setCurrentText(self.cfg.get("ptt_output", "none"))
        layout.addRow("PTT Output", self.ptt_mode_combo)

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
        self.chk_no_hotkey.setChecked(False)
        self.chk_dry_run = QCheckBox("Dry run")
        self.chk_dry_run.setChecked(False)
        layout.addWidget(self.chk_no_hotkey)
        layout.addWidget(self.chk_dry_run)
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
        self.lbl_waydroid = QLabel("-")
        self.lbl_ydotool = QLabel("-")
        layout.addRow("Platform", self.lbl_platform)
        layout.addRow("Session", self.lbl_session)
        layout.addRow("Waydroid", self.lbl_waydroid)
        layout.addRow("ydotool", self.lbl_ydotool)
        return group

    def _wrap(self, layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    def log(self, message: str):
        self.log_view.appendPlainText(message)
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cursor)

    def update_env_status(self):
        self.lbl_platform.setText(platform.system())
        session = os.environ.get("XDG_SESSION_TYPE", "n/a")
        self.lbl_session.setText(session)
        self.lbl_waydroid.setText("Yes" if os.environ.get("WAYDROID_SESSION") else "No")
        ydotool = any(Path(p).exists() for p in ["/usr/bin/ydotool", "/usr/local/bin/ydotool"])
        self.lbl_ydotool.setText("Yes" if ydotool else "No")
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
        current_in = self.audio_in_combo.currentText()
        current_out = self.audio_out_combo.currentText()
        self.audio_in_combo.clear()
        self.audio_out_combo.clear()

        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            try:
                list_audio_devices()
            except Exception as e:
                self.log(f"Audio refresh failed: {e}")
                return
        entries = []
        for line in buf.getvalue().splitlines():
            if "] " in line:
                entries.append(line.split("] ", 1)[1].split(" (hostapi=", 1)[0])
        for name in entries:
            self.audio_in_combo.addItem(name)
            self.audio_out_combo.addItem(name)

        self._restore_combo(self.audio_in_combo, current_in or self.cfg.get("audio_input"))
        self._restore_combo(self.audio_out_combo, current_out or self.cfg.get("audio_output"))
        self.log("Audio devices refreshed.")

    def _restore_combo(self, combo: QComboBox, value: Optional[str]):
        if not value:
            return
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

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
        payload["ptt_hotkey"] = self.hotkey_edit.text().strip() or "F9"
        payload["ptt_output"] = self.ptt_mode_combo.currentText()
        payload["no_hotkey"] = self.chk_no_hotkey.isChecked()
        payload["dry_run"] = self.chk_dry_run.isChecked()
        return payload

    def save_config(self):
        import json

        payload = self.config_payload()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
            f.write("\n")
        self.cfg = payload
        self.log(f"Saved config to {CONFIG_PATH}")

    def _base_args(self):
        args = ["-m", "zpttlink", "--serial", self.serial_combo.currentData() or self.serial_combo.currentText().split(" — ", 1)[0]]
        hotkey = self.hotkey_edit.text().strip()
        if hotkey:
            args.extend(["--key", hotkey])
        ptt_mode = self.ptt_mode_combo.currentText()
        if ptt_mode and ptt_mode != "none":
            args.extend(["--ptt-output", ptt_mode])
        if self.chk_no_hotkey.isChecked():
            args.append("--no-hotkey")
        if self.chk_dry_run.isChecked():
            args.append("--dry-run")
        return args

    def start_runtime(self):
        if self.proc:
            self.log("Runtime already running.")
            return
        self.save_config()
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
        proc.readyReadStandardOutput.connect(lambda: self.log(bytes(proc.readAllStandardOutput()).decode(errors="replace").strip()))
        proc.readyReadStandardError.connect(lambda: self.log(bytes(proc.readAllStandardError()).decode(errors="replace").strip()))
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
    window = MainWindow()
    window.show()
    return app.exec()
