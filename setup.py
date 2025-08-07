from setuptools import setup, find_packages

setup(
    name="zpttlink",
    version="1.0.0",
    description="Bridge Zello via BlueStacks to radio hardware using AIOC and Python",
    author="Max Hayim",
    packages=find_packages(),
    install_requires=[
        "pyserial",
        "pynput",
        "sounddevice",
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