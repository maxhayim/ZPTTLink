from .cm108 import CM108Radio
from .digirig import DigiRigRadio
from .signalink import SignalinkRadio

def get_radio(config):
    mode = config.get("radio_type", "auto")

    if mode == "cm108":
        return CM108Radio(config)

    if mode == "digirig":
        return DigiRigRadio(config)

    if mode == "signalink":
        return SignalinkRadio(config)

    # AUTO
    if "aioc" in config.get("com_port", "").lower():
        return CM108Radio(config)

    return DigiRigRadio(config)
