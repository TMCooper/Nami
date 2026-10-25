"""Starts AnimeSamaApi's Flask app for Nami.

AnimeSamaApi's own main.py runs a git check that waits on input() when the clone is behind
origin (it hangs or crashes when launched without a console), and enables Flask debug mode
with the reloader. This launcher runs the same app without either.
Run with the AnimeSamaApi folder as the working directory.
"""
import os
import sys
import logging
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    sys.path.insert(0, os.getcwd())
    from src.api import Yui
    from src.utils.config import Config

    # Used by AnimeSamaApi's scan endpoints to call themselves
    Config.IP = args.host
    Config.PORT = args.port

    # Errors only in data/logs/animesama.log (one access line per request otherwise)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    Yui.app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
