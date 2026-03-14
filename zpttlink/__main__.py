import sys

if __name__ == "__main__":
    if "--gui" in sys.argv:
        argv = [arg for arg in sys.argv[1:] if arg != "--gui"]
        from .gui import launch_gui

        raise SystemExit(launch_gui(argv))
    else:
        from .main import main

        main()
