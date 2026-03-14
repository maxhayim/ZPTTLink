import sys


def main_entry():
    if "--gui" in sys.argv:
        argv = [arg for arg in sys.argv if arg != "--gui"]
        from .gui import launch_gui

        raise SystemExit(launch_gui(argv))

    from .main import main

    main()


if __name__ == "__main__":
    main_entry()
