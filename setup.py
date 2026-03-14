from setuptools import setup, find_packages

setup(
    name="zpttlink",
    version="2.0.0",
    description="Bridge Zello to radio hardware using AIOC and Python",
    author="Max Hayim",
    packages=find_packages(),
    install_requires=[
        "pyserial",
        "pynput",
        "sounddevice",
        "numpy",
        "loguru",
        "platformdirs",
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