import socket
import multiprocessing
import os
import time
import urllib.request

import webview

import engine
from core.realtime_gateway import LocalRealtimeGateway
from core.updater import (
    UPDATE_MANIFEST_URL,
    check_for_update as fetch_update,
    download_and_verify,
    launch_installer,
)
from ui.web_dashboard import WebDashboardController


def run_server_process():
    controller = WebDashboardController()
    gateway = LocalRealtimeGateway(
        history_provider=engine.realtime_history,
        authenticator=engine.authorize_overlay_path,
        logger=lambda message: controller.record_operational_log(message, "cyan"),
    )
    engine.set_dashboard_controller(controller)
    engine.set_realtime_gateway(gateway)
    gateway.start()
    try:
        engine.run_flask()
    finally:
        controller.shutdown()
        gateway.stop()
        engine.set_realtime_gateway(None)


class DesktopAPI:
    def __init__(self, server_process):
        self._server_process = server_process
        self._window = None
        self._closed = False
        self._pending_update = None

    def check_for_update(self):
        if not UPDATE_MANIFEST_URL:
            return {
                "ok": False,
                "message": "Esta build ainda não possui o endereço do manifesto de atualizações.",
            }
        try:
            update = fetch_update()
        except Exception as error:
            return {"ok": False, "message": f"Não foi possível verificar atualizações: {error}"}
        if update is None:
            self._pending_update = None
            return {"ok": True, "available": False, "current_version": "1.3.0"}
        self._pending_update = update
        return {
            "ok": True,
            "available": True,
            "version": update.version,
            "notes_url": update.notes_url,
        }

    def install_update(self):
        update = self._pending_update
        if update is None:
            return {"ok": False, "message": "Nenhuma atualização pendente."}
        try:
            installer = download_and_verify(update)
            launch_installer(installer)
        except Exception as error:
            return {"ok": False, "message": f"Não foi possível preparar a atualização: {error}"}
        self.shutdown()
        if self._window is not None:
            self._window.destroy()
        return {"ok": True, "message": "Atualização iniciada."}

    def close_app(self):
        self.shutdown()
        if self._window is not None:
            self._window.destroy()
        return True

    def choose_overlay_file(self, mode="open", default_name="netrunner-overlay.json"):
        """Use the native picker so export/import never depends on a browser download folder."""
        if self._window is None:
            return {"ok": False, "message": "Janela ainda não está disponível."}
        try:
            dialog = webview.SAVE_DIALOG if mode == "save" else webview.OPEN_DIALOG
            kwargs = {"file_types": ("Overlay JSON (*.json)",)}
            if mode == "save":
                kwargs["save_filename"] = default_name
            result = self._window.create_file_dialog(dialog, **kwargs)
            path = result[0] if isinstance(result, (list, tuple)) and result else result
            return {"ok": bool(path), "path": path or "", "cancelled": not bool(path)}
        except Exception as error:
            return {"ok": False, "message": f"Não foi possível abrir o seletor de arquivos: {error}"}

    def read_overlay_file(self, path):
        try:
            with open(os.path.abspath(path), "r", encoding="utf-8") as handle:
                return {"ok": True, "content": handle.read()}
        except (OSError, UnicodeError) as error:
            return {"ok": False, "message": f"Não foi possível ler o overlay: {error}"}

    def write_overlay_file(self, path, content):
        try:
            destination = os.path.abspath(path)
            with open(destination, "w", encoding="utf-8") as handle:
                handle.write(str(content))
            return {"ok": True, "path": destination, "message": "Overlay exportado."}
        except OSError as error:
            return {"ok": False, "message": f"Não foi possível exportar o overlay: {error}"}

    def import_overlay_file(self):
        pick = self.choose_overlay_file("open")
        if not pick.get("ok"):
            return pick
        return self.read_overlay_file(pick["path"])

    def export_overlay_file(self, content, default_name="netrunner-overlay.json"):
        pick = self.choose_overlay_file("save", default_name)
        if not pick.get("ok"):
            return pick
        return self.write_overlay_file(pick["path"], content)

    def shutdown(self, *_):
        if self._closed:
            return
        self._closed = True
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:5000/api/shutdown",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "X-Netrunner-Admin-Token": engine.admin_token(),
                },
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
    engine.ensure_security_manager()
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
        "Netrunner Overlay Engine v1.3.0",
        engine.dashboard_url(),
        width=1540,
        height=960,
        min_size=(1180, 720),
        background_color="#020817",
        text_select=True,
    )
    api._window = window
    window.expose(
        api.close_app,
        api.check_for_update,
        api.install_update,
        api.import_overlay_file,
        api.export_overlay_file,
    )
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
