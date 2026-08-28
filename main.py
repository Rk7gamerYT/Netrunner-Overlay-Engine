import os
import sys
import threading
import time
import html as html_utils
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
    QLineEdit,
    QTabWidget,
    QSplitter,
    QFrame,
    QTextBrowser
)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon


# ==========================================
# IMPORT DOS BOTS
# ==========================================

from bots.twitch import TwitchBot
from bots.youtube import YouTubeBot
from bots.tiktok import TikTokBot
from bots.kick import KickBot


def resource_path(relative_path):
    """Resolve recursos tanto no código-fonte quanto no executável PyInstaller."""

    base_path = getattr(
        sys,
        "_MEIPASS",
        os.path.dirname(os.path.abspath(__file__))
    )

    return os.path.join(base_path, relative_path)


# ==========================================
# FLASK
# ==========================================

app = Flask(__name__)

CORS(app)

CHAT_MESSAGES = []

MAX_MESSAGES = 50

CHAT_LOCK = threading.Lock()

MESSAGE_SEQUENCE = int(time.time() * 1000) * 1000


# ==========================================
# OVERLAY DEFAULTS
# ==========================================

LIVE_HTML = """
<div id="log"></div>

<script
type="text/template"
id="chatlist_item"
>

<div
    class="chat-message {platform}"
    data-id="{messageId}"
>

    <span
        class="platform-icon"
        title="{platformLabel}"
    >
        {icon}
    </span>

    <span
        class="name"
        style="color:{color}"
    >
        {from}
    </span>

    <span class="colon">
        :
    </span>

    <span class="message">
        {message}
    </span>

</div>

</script>
"""


LIVE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Courier+Prime&display=swap');

body {
    margin: 0;
    padding: 20px;
    background: transparent;
    font-family: 'Courier Prime', monospace;
    /* Garante que o body não limite o crescimento, 
       mas que o log tenha sua própria área de scroll */
    height: 100vh;
    box-sizing: border-box;
}

#log {
    display: flex;
    flex-direction: column; /* As mensagens começam no topo e descem */
    gap: 12px;
    
    /* Define uma altura máxima e permite o scroll dentro desse container */
    height: 100%; 
    overflow-y: auto;
    
    /* Esconde a barra de rolagem visualmente */
    scrollbar-width: none;
    -ms-overflow-style: none;
}

/* Esconder barra de scroll no Chrome/Safari/Edge */
#log::-webkit-scrollbar {
    display: none;
}

.chat-message {
    /* Tamanho dinâmico */
    display: inline-block;
    width: fit-content; 
    max-width: 90%;
    
    /* Visual Minimalista */
    background: rgba(0, 0, 0, 0.7);
    padding: 10px 15px;
    border-radius: 8px;
    border: 1px solid #ff0000;
    
    /* Animação Neon Pulsante */
    animation: fadeIn 0.3s ease, neonPulse 1.5s infinite alternate;
}

.name {
    font-weight: bold;
    color: #ff4d4d;
    margin-right: 5px;
}

.platform-icon {
    margin-right: 6px;
    font-size: 13px;
}

.colon {
    color: #ff4d4d;
    margin-right: 5px;
}

.message {
    color: white;
}

/* Animações */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes neonPulse {
    from { box-shadow: 0 0 5px #ff0000; border-color: #ff0000; }
    to { box-shadow: 0 0 15px #ff0000; border-color: #ff4d4d; }
}
"""

LIVE_JS = """
let lastMessageId = 0;

let updateInProgress = false;


function escapeHtml(text) {

    const div = document.createElement("div");

    div.innerText = text;

    return div.innerHTML;
}


function addChatMessage(

    from,
    message,
    platform = "default",
    messageId = Date.now()
) {

    const template = document
        .getElementById("chatlist_item")
        .innerHTML;

    const colors = {

        twitch: "#9146ff",

        youtube: "#ff0000",

        tiktok: "#ff0050",

        kick: "#53fc18",

        default: "#ff4d4d"
    };

    const color =
        colors[platform] || colors.default;

    const icons = {

        twitch: "🟣",

        youtube: "🔴",

        tiktok: "🎵",

        kick: "🟢",

        default: "💬"
    };

    const labels = {

        twitch: "Twitch",

        youtube: "YouTube",

        tiktok: "TikTok",

        kick: "Kick",

        default: "Chat"
    };

    const icon =
        icons[platform] || icons.default;

    const platformLabel =
        labels[platform] || labels.default;

    const html = template

        .replace(
            /{icon}/g,
            icon
        )

        .replace(
            /{platformLabel}/g,
            platformLabel
        )

        .replace(
            /{from}/g,
            escapeHtml(from)
        )

        .replace(
            /{message}/g,
            escapeHtml(message)
        )

        .replace(
            /{color}/g,
            color
        )

        .replace(
            /{platform}/g,
            platform
        )

        .replace(
            /{messageId}/g,
            messageId
        );

    const wrapper = document.createElement("div");

    wrapper.innerHTML = html;

    const log =
        document.getElementById("log");

    const element =
        wrapper.firstElementChild;

    log.appendChild(element);

    while (log.children.length > 50) {

        log.removeChild(
            log.firstChild
        );
    }

    log.scrollTop = log.scrollHeight;
}


async function updateChat() {

    if (updateInProgress) {
        return;
    }

    updateInProgress = true;

    const controller = new AbortController();

    const timeoutId = setTimeout(
        () => controller.abort(),
        3000
    );

    try {

        const response = await fetch(
            `/chat?after=${lastMessageId}&t=${Date.now()}`,
            {
                cache: "no-store",
                signal: controller.signal
            }
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        data.forEach(msg => {

            const messageId = Number(msg.id);

            if (!Number.isFinite(messageId)) {
                return;
            }

            addChatMessage(

                msg.user,

                msg.message,

                msg.platform,

                messageId
            );

            lastMessageId = Math.max(
                lastMessageId,
                messageId
            );
        });

    } catch (e) {

        if (e.name !== "AbortError") {

            console.error(
                "Overlay Error:",
                e
            );
        }

    } finally {

        clearTimeout(timeoutId);

        updateInProgress = false;
    }
}

updateChat();

setInterval(updateChat, 1000);
"""


# ==========================================
# TEMPLATE
# ==========================================

OVERLAY_TEMPLATE = """
<!DOCTYPE html>

<html lang="pt-br">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<style>

{{ css|safe }}

</style>

</head>

<body>

{{ html|safe }}

<script>

{{ js|safe }}

</script>

</body>

</html>
"""


# ==========================================
# ROUTES
# ==========================================

@app.route("/")
def overlay():

    return render_template_string(

        OVERLAY_TEMPLATE,

        html=LIVE_HTML,

        css=LIVE_CSS,

        js=LIVE_JS
    )


@app.route("/chat")
def chat():

    after = request.args.get(
        "after",
        default=0,
        type=int
    )

    with CHAT_LOCK:

        messages = [

            item.copy()

            for item in CHAT_MESSAGES

            if item.get("id", 0) > after
        ]

    response = jsonify(messages)

    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )

    return response


# ==========================================
# FLASK THREAD
# ==========================================

def run_flask():

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=False,

        threaded=True,

        use_reloader=False
    )


# ==========================================
# MAIN APP
# ==========================================

class MainApp(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "Netrunner Overlay Engine"
        )

        self.setMinimumSize(
            1400,
            900
        )

        self.bots = []

        self.is_closing = False

        self.is_capturing = False

        self.is_stopping_capture = False

        self.stop_capture_attempts = 0

        self.apply_styles()

        threading.Thread(
            target=run_flask,
            daemon=True
        ).start()

        self.init_ui()


    # ==========================================
    # STYLES
    # ==========================================

    def apply_styles(self):

        self.setStyleSheet("""

        QMainWindow {

            background-color: #0b0b0b;
        }

        QLabel {

            color: #ff4d4d;

            font-size: 12px;

            font-weight: bold;

            font-family: Consolas;
        }

        QLineEdit {

            background-color: #111111;

            border: 1px solid #2a2a2a;

            border-radius: 10px;

            padding: 10px;

            color: white;

            font-size: 13px;
        }

        QLineEdit:focus {

            border: 1px solid #ff0033;

            background-color: #151515;
        }

        QPushButton {

            background-color: #ff0033;

            color: white;

            border: none;

            border-radius: 12px;

            padding: 12px;

            font-weight: bold;

            font-size: 13px;
        }

        QPushButton:hover {

            background-color: #ff3355;
        }

        QPushButton:pressed {

            background-color: #990022;
        }

        QPushButton#exitButton {

            background-color: #3a1118;

            border: 1px solid #7a2635;
        }

        QPushButton#exitButton:hover {

            background-color: #b00020;
        }

        QTextEdit {

            background-color: #111111;

            color: #00ff88;

            border: 1px solid #222222;

            border-radius: 12px;

            padding: 10px;

            font-family: Consolas;

            font-size: 12px;
        }

        QTabWidget::pane {

            border: 1px solid #222222;

            border-radius: 12px;

            background-color: #0f0f0f;
        }

        QTabBar::tab {

            background-color: #161616;

            color: #999999;

            padding: 10px 18px;

            margin-right: 5px;

            border-top-left-radius: 8px;

            border-top-right-radius: 8px;
        }

        QTabBar::tab:selected {

            background-color: #ff0033;

            color: white;
        }

        QFrame#previewFrame {

            background-color: #090909;

            border: 1px solid #282828;

            border-radius: 12px;
        }

        QSplitter::handle {

            background-color: #202020;

            width: 6px;
        }

        """)


    # ==========================================
    # UI
    # ==========================================

    def init_ui(self):

        main_layout = QVBoxLayout()


        # ==========================================
        # HEADER
        # ==========================================

        title = QLabel(
            "NETRUNNER OVERLAY ENGINE"
        )

        title.setStyleSheet("""

        font-size: 24px;

        font-weight: bold;

        color: #ff0033;

        padding: 10px;
        """)

        title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        main_layout.addWidget(title)

        splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        control_panel = QWidget()

        layout = QVBoxLayout(control_panel)


        # ==========================================
        # BOT CONFIG
        # ==========================================

        bots_label = QLabel(
            "🔴 CONFIGURAÇÃO DOS BOTS"
        )

        layout.addWidget(bots_label)

        self.input_twitch = QLineEdit()

        self.input_twitch.setPlaceholderText(
            "🟣 Canal Twitch"
        )

        self.input_youtube = QLineEdit()

        self.input_youtube.setPlaceholderText(
            "🔴 URL YouTube"
        )

        self.input_tiktok = QLineEdit()

        self.input_tiktok.setPlaceholderText(
            "⚫ Canal TikTok"
        )

        self.input_kick = QLineEdit()

        self.input_kick.setPlaceholderText(
            "🟢 Canal Kick"
        )

        layout.addWidget(self.input_twitch)

        layout.addWidget(self.input_youtube)

        layout.addWidget(self.input_tiktok)

        layout.addWidget(self.input_kick)


        # ==========================================
        # START BUTTON
        # ==========================================

        self.btn_start = QPushButton(
            "🚀 INICIAR CAPTURA"
        )

        self.btn_start.clicked.connect(
            self.start_bots
        )

        layout.addWidget(self.btn_start)


        # ==========================================
        # OVERLAY EDITOR
        # ==========================================

        editor_label = QLabel(
            "🎨 EDITOR DO OVERLAY"
        )

        layout.addWidget(editor_label)

        self.tabs = QTabWidget()

        self.html_editor = QTextEdit()

        self.html_editor.setPlainText(
            LIVE_HTML
        )

        self.css_editor = QTextEdit()

        self.css_editor.setPlainText(
            LIVE_CSS
        )

        self.js_editor = QTextEdit()

        self.js_editor.setPlainText(
            LIVE_JS
        )

        self.tabs.addTab(
            self.html_editor,
            "🌐 HTML"
        )

        self.tabs.addTab(
            self.css_editor,
            "🎨 CSS"
        )

        self.tabs.addTab(
            self.js_editor,
            "⚡ JS"
        )

        layout.addWidget(self.tabs)


        # ==========================================
        # APPLY BUTTON
        # ==========================================

        self.btn_apply = QPushButton(
            "💾 APLICAR ALTERAÇÕES"
        )

        self.btn_apply.clicked.connect(
            self.apply_overlay_changes
        )

        layout.addWidget(self.btn_apply)


        # ==========================================
        # LOGS
        # ==========================================

        logs_label = QLabel(
            "📡 LOGS DO SISTEMA"
        )

        layout.addWidget(logs_label)

        self.logs = QTextEdit()

        self.logs.setReadOnly(True)

        layout.addWidget(self.logs)


        # ==========================================
        # OBS CHAT PREVIEW
        # ==========================================

        preview_frame = QFrame()

        preview_frame.setObjectName(
            "previewFrame"
        )

        preview_layout = QVBoxLayout(
            preview_frame
        )

        preview_label = QLabel(
            "💬 CHAT AO VIVO"
        )

        preview_layout.addWidget(
            preview_label
        )

        preview_hint = QLabel(
            "Mensagens recebidas e enviadas ao overlay do OBS"
        )


        preview_hint.setStyleSheet("""

            color: #777777;

            font-size: 11px;

            font-weight: normal;
        """)

        preview_layout.addWidget(
            preview_hint
        )

        self.chat_preview = QTextBrowser()

        self.chat_preview.setReadOnly(True)

        self.chat_preview.setOpenExternalLinks(False)

        self.chat_preview.setMinimumWidth(480)

        preview_layout.addWidget(
            self.chat_preview,
            1
        )

        preview_actions = QHBoxLayout()

        self.btn_copy_obs = QPushButton(
            "📋 COPIAR LINK DO OBS"
        )

        self.btn_copy_obs.clicked.connect(
            self.copy_obs_link
        )

        preview_actions.addWidget(
            self.btn_copy_obs
        )

        self.btn_exit = QPushButton(
            "❌ FECHAR APLICAÇÃO"
        )

        self.btn_exit.setObjectName(
            "exitButton"
        )

        self.btn_exit.clicked.connect(
            self.shutdown_app
        )

        preview_actions.addWidget(
            self.btn_exit
        )

        preview_layout.addLayout(
            preview_actions
        )

        splitter.addWidget(control_panel)

        splitter.addWidget(preview_frame)

        splitter.setStretchFactor(0, 3)

        splitter.setStretchFactor(1, 2)

        splitter.setSizes([820, 580])

        main_layout.addWidget(splitter, 1)


        # ==========================================
        # ROOT
        # ==========================================

        root = QWidget()

        root.setLayout(main_layout)

        self.setCentralWidget(root)

        self.reload_preview()


    # ==========================================
    # APP ACTIONS
    # ==========================================

    def copy_obs_link(self):

        link = "http://127.0.0.1:5000"

        QApplication.clipboard().setText(
            link
        )

        self.logs.append(
            f"📋 Link do OBS copiado: {link}"
        )


    def shutdown_app(self):

        self.logs.append(
            "⏻ Encerrando aplicação..."
        )

        self.close()


    # ==========================================
    # OBS CHAT PREVIEW
    # ==========================================

    def reload_preview(self):

        colors = {

            "twitch": "#9146ff",

            "youtube": "#ff0000",

            "tiktok": "#ff0050",

            "kick": "#53fc18"
        }

        icons = {

            "twitch": "🟣",

            "youtube": "🔴",

            "tiktok": "🎵",

            "kick": "🟢"
        }

        messages = []

        with CHAT_LOCK:

            chat_snapshot = [

                item.copy()

                for item in CHAT_MESSAGES
            ]

        for item in chat_snapshot:

            platform = item.get(
                "platform",
                "default"
            )

            color = colors.get(
                platform,
                "#ff4d4d"
            )

            icon = icons.get(
                platform,
                "💬"
            )

            user = html_utils.escape(
                str(item.get("user", "Usuário"))
            )

            message = html_utils.escape(
                str(item.get("message", ""))
            )

            messages.append(f"""

            <div style="
                background: #101010;
                border: 1px solid {color};
                border-radius: 8px;
                margin: 6px 2px;
                padding: 10px 12px;
            ">
                <span style="margin-right: 6px;">
                    {icon}
                </span>
                <span style="color: {color}; font-weight: 700;">
                    {user}:
                </span>
                <span style="color: #ffffff;">
                    {message}
                </span>
            </div>
            """)

        if not messages:

            messages.append("""

            <div style="
                color: #777777;
                text-align: center;
                padding: 40px 12px;
            ">
                As mensagens enviadas ao OBS aparecerão aqui.
            </div>
            """)

        self.chat_preview.setHtml(
            """
            <html>
            <body style="
                background: #080808;
                font-family: Consolas, monospace;
                margin: 8px;
            ">
            """
            + "".join(messages)
            + "</body></html>"
        )

        scrollbar = self.chat_preview.verticalScrollBar()

        scrollbar.setValue(
            scrollbar.maximum()
        )


    # ==========================================
    # APPLY OVERLAY
    # ==========================================

    def apply_overlay_changes(self):

        global LIVE_HTML
        global LIVE_CSS
        global LIVE_JS

        LIVE_HTML = self.html_editor.toPlainText()

        LIVE_CSS = self.css_editor.toPlainText()

        LIVE_JS = self.js_editor.toPlainText()

        self.logs.append(
            "🎨 Overlay atualizado."
        )

        self.reload_preview()


    # ==========================================
    # START BOTS
    # ==========================================

    def start_bots(self):

        if self.is_stopping_capture:
            return

        if self.is_capturing:

            self.stop_capture()

            return

        configs = [

            (
                TwitchBot,
                self.input_twitch.text().strip()
            ),

            (
                YouTubeBot,
                self.input_youtube.text().strip()
            ),

            (
                TikTokBot,
                self.input_tiktok.text().strip()
            ),

            (
                KickBot,
                self.input_kick.text().strip()
            )
        ]

        active_configs = [

            (bot_class, channel)

            for bot_class, channel in configs

            if channel
        ]

        if not active_configs:

            self.logs.append(
                "⚠️ Informe ao menos um canal para iniciar a captura."
            )

            return

        self.bots = [

            bot

            for bot in self.bots

            if bot.isRunning()
        ]

        existing_bot_types = {

            type(bot)

            for bot in self.bots
        }

        started_bots = []

        for bot_class, channel in active_configs:

            if bot_class in existing_bot_types:

                self.logs.append(
                    f"⏳ {bot_class.__name__} ainda está encerrando. Tente reconectar em instantes."
                )

                continue

            try:

                bot = bot_class(channel)

                bot.new_message.connect(
                    self.receive_message
                )

                bot.status_update.connect(
                    self.receive_status
                )

                bot.finished.connect(
                    self.capture_bot_finished
                )

                self.bots.append(bot)

                started_bots.append(bot)

                bot.start()

                self.logs.append(
                    f"✅ {bot_class.__name__} iniciado."
                )

            except Exception as e:

                self.logs.append(
                    f"❌ Erro iniciando bot: {e}"
                )

        if started_bots:

            self.is_capturing = True

            self.btn_start.setText(
                "⏹ ENCERRAR CAPTURA"
            )

            self.logs.append(
                "📡 Captura iniciada."
            )


    # ==========================================
    # STOP / RECONNECT CAPTURE
    # ==========================================

    def stop_capture(self):

        if self.is_stopping_capture:
            return

        self.is_stopping_capture = True

        self.is_capturing = False

        self.stop_capture_attempts = 0

        self.btn_start.setEnabled(False)

        self.btn_start.setText(
            "⏳ ENCERRANDO CAPTURA..."
        )

        self.logs.append(
            "⏹ Encerrando captura..."
        )

        for bot in self.bots:

            try:

                bot.running = False

                bot.requestInterruption()

            except Exception:
                pass

        QTimer.singleShot(
            100,
            self.finish_stop_capture
        )


    def finish_stop_capture(self):

        running_bots = [

            bot

            for bot in self.bots

            if bot.isRunning()
        ]

        if running_bots and self.stop_capture_attempts < 20:

            self.stop_capture_attempts += 1

            QTimer.singleShot(
                100,
                self.finish_stop_capture
            )

            return

        self.bots = running_bots

        self.is_stopping_capture = False

        self.btn_start.setEnabled(True)

        self.btn_start.setText(
            "↻ INICIAR / RECONECTAR CAPTURA"
        )

        self.logs.append(
            "✅ Captura encerrada. Você pode alterar os canais e reconectar."
        )

        if running_bots:

            self.logs.append(
                f"⏳ {len(running_bots)} conexão(ões) ainda finalizando em segundo plano."
            )


    def capture_bot_finished(self):

        finished_bot = self.sender()

        if finished_bot in self.bots:

            self.bots.remove(finished_bot)

        if self.is_stopping_capture or not self.is_capturing:
            return

        if any(

            bot.isRunning() and bot.running

            for bot in self.bots
        ):
            return

        self.is_capturing = False

        self.btn_start.setText(
            "↻ INICIAR / RECONECTAR CAPTURA"
        )

        self.logs.append(
            "⚠️ Todas as capturas foram encerradas."
        )


    # ==========================================
    # RECEIVE MESSAGE
    # ==========================================

    def receive_message(

        self,
        user,
        message,
        platform
    ):

        self.logs.append(
            f"[{platform.upper()}] {user}: {message}"
        )

        global MESSAGE_SEQUENCE

        with CHAT_LOCK:

            MESSAGE_SEQUENCE += 1

            CHAT_MESSAGES.append({

                "id": MESSAGE_SEQUENCE,

                "user": user,

                "message": message,

                "platform": platform
            })

            while len(CHAT_MESSAGES) > MAX_MESSAGES:

                CHAT_MESSAGES.pop(0)

        self.reload_preview()


    # ==========================================
    # STATUS
    # ==========================================

    def receive_status(self, status):

        self.logs.append(status)


    # ==========================================
    # CLOSE EVENT
    # ==========================================

    def closeEvent(self, event):

        if self.is_closing:

            event.accept()

            return

        self.is_closing = True

        for bot in self.bots:

            try:

                bot.running = False

                bot.requestInterruption()

            except:

                pass

        for bot in self.bots:

            try:

                if not bot.wait(1500):

                    bot.terminate()

                    bot.wait(500)

            except:

                pass

        self.bots.clear()

        event.accept()

        QApplication.quit()


# ==========================================
# START APP
# ==========================================

if __name__ == "__main__":

    qt = QApplication(sys.argv)

    qt.setApplicationName("Netrunner Overlay Engine")

    app_icon = QIcon(
        resource_path(
            os.path.join("assets", "netrunner.ico")
        )
    )

    qt.setWindowIcon(app_icon)

    window = MainApp()

    window.setWindowIcon(app_icon)

    window.show()

    sys.exit(qt.exec())
