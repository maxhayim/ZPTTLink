# zpttlink/ptt.py

import serial
import threading

class PTTListener:
    def __init__(self, port, baudrate=9600, callback=None):
        self.port = port
        self.baudrate = baudrate
        self.callback = callback
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.listen, daemon=True)
        self.thread.start()

    def listen(self):
        try:
            with serial.Serial(self.port, self.baudrate, timeout=1) as ser:
                print(f"[PTT] Listening on {self.port}")
                while self.running:
                    line = ser.readline().decode().strip()
                    if line and self.callback:
                        print(f"[PTT] Trigger received: {line}")
                        self.callback(line)
        except serial.SerialException as e:
            print(f"[PTT] Serial error: {e}")

    def stop(self):
        self.running = False
