from PySide6.QtCore import QThread, Signal

class BaseBot(QThread):
    # Sinal para enviar mensagens para a UI
    new_message = Signal(str, str, str)  # user, text, platform
    # Sinal para avisar status (ex: "Conectado", "Erro")
    status_update = Signal(str)

    def __init__(self, channel_name):
        super().__init__()
        self.channel_name = channel_name
        self.running = False

    def stop(self):
        self.running = False
        self.wait() # Aguarda a thread fechar corretamente