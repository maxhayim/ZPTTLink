import logging
logger = logging.getLogger("ZPTTLink")

def init(com_port, hotkey):
    logger.info(f"Listening for PTT on {com_port} (Hotkey: {hotkey})")
    # TODO: Initialize serial port or USB listener

def check_ptt():
    # TODO: Replace with actual PTT detection
    return False
