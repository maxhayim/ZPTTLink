import usb.core
from .base import RadioInterface

class CM108Radio(RadioInterface):
    def open(self):
        self.dev = usb.core.find(idVendor=0x0d8c)
        if self.dev is None:
            raise RuntimeError("CM108 device not found")

    def ptt_on(self):
        self.dev.ctrl_transfer(0x21, 0x09, 0x0200, 0, [0x04])

    def ptt_off(self):
        self.dev.ctrl_transfer(0x21, 0x09, 0x0200, 0, [0x00])

    def close(self):
        pass
