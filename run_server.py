import os

from waitress import serve

from app import app
from gpswv_location import start_gpswv_location_poller
from jt808_server import start_jt808_server


if __name__ == "__main__":
    host = os.environ.get("FARM_SYSTEM_HOST", "0.0.0.0")
    port = int(os.environ.get("FARM_SYSTEM_PORT", "5000"))
    gpswv_poller = start_gpswv_location_poller()
    jt808_server = start_jt808_server()
    try:
        serve(app, host=host, port=port, threads=8)
    finally:
        gpswv_poller.stop()
        jt808_server.stop()
