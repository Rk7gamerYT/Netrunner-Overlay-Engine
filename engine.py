import os
import sys
import threading
import time

from flask import Flask, jsonify, render_template_string, request

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
@app.route("/overlay")
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

        host="127.0.0.1",

        port=5000,

        debug=False,

        threaded=True,

        use_reloader=False
    )


