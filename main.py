"""
Entry point for the AVRDUDE GUI wrapper.

Run with:    python main.py

Kept tiny on purpose - all the real work lives in the other modules.
"""

import sys

import gui


def main():
    app = gui.AvrGui()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
