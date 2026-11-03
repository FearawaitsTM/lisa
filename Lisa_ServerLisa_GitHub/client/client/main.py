import os

from .app import LisaApp


def main():
    os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")
    app = LisaApp()
    app.run()


if __name__ == "__main__":
    main()
