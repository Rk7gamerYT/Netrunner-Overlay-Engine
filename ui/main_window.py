from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton, QLineEdit, QTextEdit

class NetrunnerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Netrunner App")
        self.setGeometry(100, 100, 600, 400)

        # Central widget e layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Inputs
        self.twitch_input = QLineEdit()
        self.twitch_input.setPlaceholderText("Nome do canal Twitch")
        self.layout.addWidget(self.twitch_input)

        self.youtube_input = QLineEdit()
        self.youtube_input.setPlaceholderText("URL YouTube")
        self.layout.addWidget(self.youtube_input)

        self.tiktok_input = QLineEdit()
        self.tiktok_input.setPlaceholderText("Nome do canal TikTok")
        self.layout.addWidget(self.tiktok_input)

        self.kick_input = QLineEdit()
        self.kick_input.setPlaceholderText("Nome do canal Kick")
        self.layout.addWidget(self.kick_input)

        # Botão
        self.btn_toggle = QPushButton("ENGATAR CAPTURA")
        self.layout.addWidget(self.btn_toggle)

        # Área de log
        self.log_area = QTextEdit()
        self.layout.addWidget(self.log_area)

        # Variáveis de estado
        self.running = False

    def add_message(self, user, message, platform):
        self.log_area.append(f"[{platform}] {user}: {message}")

    def update_status(self, status):
        self.statusBar().showMessage(status)