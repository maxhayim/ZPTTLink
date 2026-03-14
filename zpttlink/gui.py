import os
import platform
import sys

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports


def detect_session_type() -> str:
    if platform.system() != "Linux":
        return "n/a"
    return os.environ.get("XDG_SESSION_TYPE", "unknown")


def detect_waydroid() -> str:
    if platform.system() != "Linux":
        return "No"
    paths = [
        "/usr/bin/waydroid",
        "/var/lib/waydroid",
        "/run/waydroid-container",
    ]
    return "Yes" if any(os.path.exists(path) for path in paths) else "No"


def detect_ydotool() -> str:
    if platform.system() != "Linux":
        return "n/a"
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(path, "ydotool")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return "Yes"
    return "No"


def list_serial_devices():
    return list(list_ports.comports())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._process_finished)

        self.setWindowTitle("ZPTTLink v2.0.0")
        self.resize(980, 680)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        layout.addWidget(self._build_status_group())
        layout.addWidget(self._build_config_group())
        layout.addLayout(self._build_actions_row())
        layout.addWidget(self._build_log_group(), stretch=1)

        self.refresh_serial_devices()
        self.refresh_status()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start(5000)

    def _build_status_group(self):
        box = QGroupBox("Environment")
        grid = QGridLayout(box)

        self.os_value = QLabel("-")
        self.session_value = QLabel("-")
        self.waydroid_value = QLabel("-")
        self.ydotool_value = QLabel("-")
        self.proc_value = QLabel("Stopped")

        grid.addWidget(QLabel("OS"), 0, 0)
        grid.addWidget(self.os_value, 0, 1)
        grid.addWidget(QLabel("Session"), 0, 2)
        grid.addWidget(self.session_value, 0, 3)

        grid.addWidget(QLabel("Waydroid"), 1, 0)
        grid.addWidget(self.waydroid_value, 1, 1)
        grid.addWidget(QLabel("ydotool"), 1, 2)
        grid.addWidget(self.ydotool_value, 1, 3)

        grid.addWidget(QLabel("Core process"), 2, 0)
        grid.addWidget(self.proc_value, 2, 1, 1, 3)
        return box

    def _build_config_group(self):
        box = QGroupBox("Configuration")
        form = QFormLayout(box)

        serial_row = QHBoxLayout()
        self.serial_combo = QComboBox()
        self.serial_combo.setEditable(True)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_serial_devices)
        serial_row.addWidget(self.serial_combo, stretch=1)
        serial_row.addWidget(refresh_btn)

        self.hotkey_edit = QLineEdit("F9")
        self.ptt_output_combo = QComboBox()
        self.ptt_output_combo.addItems(["none", "dtr", "rts"])
        self.no_hotkey_check = QCheckBox("Disable hotkey injection")
        self.dry_run_check = QCheckBox("Dry run")

        form.addRow("Serial device", serial_row)
        form.addRow("Hotkey", self.hotkey_edit)
        form.addRow("PTT output", self.ptt_output_combo)
        form.addRow("", self.no_hotkey_check)
        form.addRow("", self.dry_run_check)
        return box

    def _build_actions_row(self):
        row = QHBoxLayout()

        self.test_btn = QPushButton("Test Serial PTT")
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.clear_btn = QPushButton("Clear Log")

        self.test_btn.clicked.connect(self.test_ptt)
        self.start_btn.clicked.connect(self.start_core)
        self.stop_btn.clicked.connect(self.stop_core)
        self.clear_btn.clicked.connect(self.clear_log)

        row.addWidget(self.test_btn)
        row.addWidget(self.start_btn)
        row.addWidget(self.stop_btn)
        row.addStretch(1)
        row.addWidget(self.clear_btn)
        return row

    def _build_log_group(self):
        box = QGroupBox("Logs")
        layout = QVBoxLayout(box)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_output.setMaximumBlockCount(5000)
        layout.addWidget(self.log_output)
        return box

    def refresh_status(self):
        self.os_value.setText(platform.system())
        self.session_value.setText(detect_session_type())
        self.waydroid_value.setText(detect_waydroid())
        self.ydotool_value.setText(detect_ydotool())
        self.proc_value.setText("Running" if self.process.state() != QProcess.NotRunning else "Stopped")

    def refresh_serial_devices(self):
        current = self.serial_combo.currentText().strip()
        self.serial_combo.clear()
        ports = list_serial_devices()
        for port in ports:
            text = f"{port.device}  |  {port.description}"
            self.serial_combo.addItem(text, port.device)

        if current:
            index = self.serial_combo.findText(current, Qt.MatchContains)
            if index >= 0:
                self.serial_combo.setCurrentIndex(index)
            else:
                self.serial_combo.setEditText(current)

        if not current and ports:
            self.serial_combo.setCurrentIndex(0)

        self._append_log(f"[GUI] Found {len(ports)} serial device(s).")

    def selected_serial(self):
        data = self.serial_combo.currentData()
        if data:
            return str(data)

        text = self.serial_combo.currentText().strip()
        if "  |  " in text:
            return text.split("  |  ", 1)[0].strip()
        return text

    def build_core_args(self, include_test=False):
        args = ["-m", "zpttlink"]

        serial_port = self.selected_serial()
        if serial_port:
            args.extend(["--serial", serial_port])

        hotkey = self.hotkey_edit.text().strip()
        if hotkey:
            args.extend(["--key", hotkey])

        ptt_output = self.ptt_output_combo.currentText().strip()
        if ptt_output:
            args.extend(["--ptt-output", ptt_output])

        if self.no_hotkey_check.isChecked():
            args.append("--no-hotkey")

        if self.dry_run_check.isChecked():
            args.append("--dry-run")

        if include_test:
            args.append("--test-ptt")

        return args

    def test_ptt(self):
        serial_port = self.selected_serial()
        ptt_output = self.ptt_output_combo.currentText().strip()
        if not serial_port:
            QMessageBox.warning(self, "Missing serial device", "Select a serial device first.")
            return
        if ptt_output == "none":
            QMessageBox.warning(self, "Missing PTT output", "Set PTT output to dtr or rts for a serial test.")
            return

        test_process = QProcess(self)
        test_process.readyReadStandardOutput.connect(
            lambda: self._append_log(bytes(test_process.readAllStandardOutput()).decode("utf-8", errors="replace"))
        )
        test_process.readyReadStandardError.connect(
            lambda: self._append_log(bytes(test_process.readAllStandardError()).decode("utf-8", errors="replace"))
        )
        test_process.finished.connect(lambda *_: self._append_log("[GUI] Test Serial PTT finished."))

        args = self.build_core_args(include_test=True)
        self._append_log(f"[GUI] Running test: {sys.executable} {' '.join(args)}")
        test_process.start(sys.executable, args)

    def start_core(self):
        if self.process.state() != QProcess.NotRunning:
            self._append_log("[GUI] Core is already running.")
            return

        args = self.build_core_args(include_test=False)
        self._append_log(f"[GUI] Starting core: {sys.executable} {' '.join(args)}")
        self.process.start(sys.executable, args)
        if not self.process.waitForStarted(3000):
            QMessageBox.critical(self, "Failed to start", "Could not start ZPTTLink core.")
        self.refresh_status()

    def stop_core(self):
        if self.process.state() == QProcess.NotRunning:
            self._append_log("[GUI] Core is not running.")
            return

        self._append_log("[GUI] Stopping core...")
        self.process.terminate()
        if not self.process.waitForFinished(3000):
            self.process.kill()
            self.process.waitForFinished(2000)
        self.refresh_status()

    def clear_log(self):
        self.log_output.clear()

    def _read_stdout(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._append_log(data)

    def _read_stderr(self):
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        self._append_log(data)

    def _process_finished(self, exit_code, exit_status):
        self._append_log(f"[GUI] Core exited (code={exit_code}, status={int(exit_status)}).")
        self.refresh_status()

    def _append_log(self, text: str):
        text = text.rstrip()
        if not text:
            return
        self.log_output.appendPlainText(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


def launch_gui(argv=None):
