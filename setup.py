from setuptools import setup, find_packages

setup(
    name="zpttlink",
    version="3.0.0",
    description="Open-source Zello <-> radio/Asterisk linking bridge: DTR/RTS/CM108 hardware PTT or Asterisk (USRP) over the network, with pynput/ydotool/ADB key injection for BlueStacks, Waydroid, and docker-android",
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