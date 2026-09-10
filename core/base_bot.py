import threading


class Signal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args):
        for callback in tuple(self._callbacks):
            callback(*args)

class BaseBot:

    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.running = False
        self.new_message = Signal()
        # Eventos de plataforma (doações, inscrições, follows, gifts etc.).
        # Mantemos o sinal separado do chat para que cada tipo tenha seu próprio
        # overlay e endpoint.
        self.new_event = Signal()
        self.status_update = Signal()
        self.finished = Signal()
        self._thread = None

    def _run_wrapper(self):
        try:
            self.run()
        finally:
            self.running = False
            self.finished.emit()

    def start(self):
        if self.isRunning():
            return
        self._thread = threading.Thread(
            target=self._run_wrapper,
            name=f"{type(self).__name__}-{self.channel_name}",
            daemon=True,
        )
        self._thread.start()

    def isRunning(self):
        return bool(self._thread and self._thread.is_alive())

    def requestInterruption(self):
        self.running = False

    def wait(self, timeout_ms=None):
        if not self._thread:
            return True
        timeout = None if timeout_ms is None else timeout_ms / 1000
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def stop(self):
        self.running = False
        self.wait()
