import socket
import multiprocessing
import time
import urllib.request

import webview

import engine
from ui.web_dashboard import WebDashboardController


def run_server_process():
    controller = WebDashboardController()
    engine.set_dashboard_controller(controller)
    try:
        engine.run_flask()
    finally:
        controller.shutdown()


class DesktopAPI:
    def __init__(self, server_process):
        self._server_process = server_process
        self._window = None
        self._closed = False

    def close_app(self):
        self.shutdown()
        if self._window is not None:
            self._window.destroy()
        return True

    def shutdown(self, *_):
        if self._closed:
            return
        self._closed = True
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:5000/api/shutdown",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(request, timeout=1).close()
        except Exception:
            pass
        if self._server_process.is_alive():
            self._server_process.join(1.5)
        if self._server_process.is_alive():
            self._server_process.terminate()
            self._server_process.join(1)


def wait_for_server(host="127.0.0.1", port=5000, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.35):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    multiprocessing.freeze_support()
    server_process = multiprocessing.Process(
        target=run_server_process,
        name="NetrunnerOverlayServer",
        daemon=True,
    )
    server_process.start()

    if not wait_for_server(timeout=20):
        server_process.terminate()
        server_process.join(1)
        raise RuntimeError("Não foi possível iniciar o servidor local na porta 5000.")

    api = DesktopAPI(server_process)
    window = webview.create_window(
        "Netrunner Overlay Engine v1.2.0",
        "http://127.0.0.1:5000/dashboard",
        width=1540,
        height=960,
        min_size=(1180, 720),
        background_color="#020817",
        text_select=True,
    )
    api._window = window
    window.expose(api.close_app)
    window.events.closed += api.shutdown

    try:
        webview.start(
            debug=False,
            private_mode=True,
            icon=engine.resource_path("assets/netrunner.ico"),
        )
    finally:
        api.shutdown()


if __name__ == "__main__":
    main()
