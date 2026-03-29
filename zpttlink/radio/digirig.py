import serial
from .base import RadioInterface

class DigiRigRadio(RadioInterface):
    def open(self):
        self.ser = serial.Serial(self.config["com_port"], 9600)

    def ptt_on(self):
        self.ser.rts = True

    def ptt_off(self):
        self.ser.rts = False

    def close(self):
        self.ser.close()
