from setuptools import setup, find_packages

setup(
    name="zpttlink",
    version="2.1.0",
    description="Zello <-> radio PTT gateway with deterministic DTR/RTS/CM108 PTT and pynput/ydotool/ADB key injection for BlueStacks, Waydroid, and docker-android",
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