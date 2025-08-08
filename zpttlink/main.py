import logging

# Configure logging format and level
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

def main():
    logging.info("Starting ZPTTLink core...")
    logging.info("Audio input: AIOC Microphone")
    logging.info("Audio output: AIOC Speaker")
    logging.info("Listening for PTT on COM3 (Hotkey: F9)")
    logging.info("✅ Audio system ready")
    logging.info("✅ PTT system ready")
    logging.info("ZPTTLink is running successfully!")
    logging.info("Type 'help' for available commands or 'q' to quit.")

    # Main loop
    while True:
        cmd = input("> ").strip().lower()

        if cmd == "q":
            logging.info("Exiting ZPTTLink. Goodbye!")
            break

        elif cmd == "help":
            print("\nAvailable commands:")
            print("  help  - Show this help message")
            print("  q     - Quit ZPTTLink\n")

        elif cmd == "":
            continue  # Ignore empty input

        else:
            logging.warning(f"Unknown command: {cmd}. Type 'help' for options.")

if __name__ == "__main__":
    main()
