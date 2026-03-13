# ZPTTLink v2.0.0 Plan

This patch adds the missing foundation pieces identified during real-world
testing on Raspberry Pi, Wayland, Waydroid, and AIOC serial PTT hardware.

## Goals

- Add direct serial PTT support using DTR and RTS.
- Add environment detection for X11, Wayland, and Waydroid.
- Add richer diagnostics for support and field testing.
- Add a first cross-platform GUI built with PySide6.
- Preserve a headless/core-first architecture.

## Included modules

- `zpttlink/serial_ptt.py`
- `zpttlink/platform_detect.py`
- `zpttlink/gui_app.py`

## Intended integration points

The existing runtime should wire these pieces in roughly this order:

1. Detect runtime environment with `detect_runtime_environment()`.
2. Load config for hotkey mode and serial PTT mode.
3. When PTT input goes active:
   - optionally inject the configured hotkey
   - optionally assert DTR or RTS on the configured serial device
4. When PTT input releases:
   - release the hotkey
   - deassert DTR or RTS

## Recommended CLI additions

Suggested flags for v2.0.0:

- `--ptt-mode hotkey|dtr|rts|hotkey+dtr|hotkey+rts`
- `--ptt-serial /dev/ttyACM0`
- `--ptt-line dtr|rts`
- `--gui`
- `--debug-env`

## Recommended logging additions

Suggested runtime messages:

- `PTT input detected from AIOC`
- `Runtime environment: wayland=True x11=False waydroid=True`
- `Opening serial PTT device /dev/ttyACM0`
- `Asserting DTR`
- `Releasing DTR`
- `Injecting hotkey F9`

## Notes

This patch is intentionally additive. It creates the new modules needed for
v2.0.0 without assuming the exact internal structure of the current runtime.
It should be integrated into the existing event loop and CLI entrypoint.
diff --git a/zpttlink/platform_detect.py b/zpttlink/platform_detect.py
