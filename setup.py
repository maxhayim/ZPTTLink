from setuptools import setup, find_packages

setup(
    name="zpttlink",
    version="4.0.0",
    description="ZPTTLink is an open-source, all-in-one linking bridge. Deterministic DTR/RTS/CM108 hardware PTT or a network Asterisk (USRP) backend, with pynput/ydotool/ADB key injection for BlueStacks, Waydroid, and docker-android. Compatible radio interfaces include the AIOC (All-In-One Cable), CM108/CM119-based USB sound fobs, DigiRig, and other USB serial/audio radio cables.",
    author="Max Hayim",
    packages=find_packages(),
    install_requires=[
        "pyserial",
        "pynput",
        "sounddevice",
        "numpy",
        "loguru",
        "platformdirs",
        "pyusb",
        "PySide6",
        "pulsectl; platform_system == 'Linux'",
        "pycaw; platform_system == 'Windows'",
        "pyobjc; platform_system == 'Darwin'"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)