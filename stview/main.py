import os

from stview import create_app


def main():
    app = create_app()
    host = os.environ.get("STVIEW_BIND", "127.0.0.1")
    port = int(os.environ.get("STVIEW_PORT", "5004"))
    debug = os.environ.get("STVIEW_DEBUG", "1") not in ("0", "false", "False")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
