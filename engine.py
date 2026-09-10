import os
import sys
import threading
import time

from flask import Flask, jsonify, render_template_string, request, send_file, send_from_directory
from waitress import serve

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
EVENT_MESSAGES = []

MAX_MESSAGES = 50

CHAT_LOCK = threading.Lock()

MESSAGE_SEQUENCE = int(time.time() * 1000) * 1000
EVENT_SEQUENCE = int(time.time() * 1000) * 1000

DASHBOARD_CONTROLLER = None


def set_dashboard_controller(controller):
    global DASHBOARD_CONTROLLER
    DASHBOARD_CONTROLLER = controller


# ==========================================
# OVERLAY DEFAULTS
# ==========================================

DEFAULT_LIVE_HTML = """
<div id="log"></div>

<script
type="text/template"
id="chatlist_item"
>

<div
    class="chat-message {platform}"
    data-id="{messageId}"
>

    <img
        class="platform-icon"
        src="{icon}"
        alt=""
        title="{platformLabel}"
    >

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

LIVE_HTML = DEFAULT_LIVE_HTML


DEFAULT_LIVE_CSS = """
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
    width: 18px;
    height: 18px;
    object-fit: contain;
    vertical-align: -4px;
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

LIVE_CSS = DEFAULT_LIVE_CSS

DEFAULT_LIVE_JS = """
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

        twitch: "/assets/platforms/twitch.png",

        youtube: "/assets/platforms/youtube.png",

        tiktok: "/assets/platforms/tiktok.png",

        kick: "/assets/platforms/kick.png",

        default: "/assets/netrunner.png"
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

LIVE_JS = DEFAULT_LIVE_JS

DEFAULT_EVENT_HTML = """
<div id="events"></div>
"""

DEFAULT_EVENT_CSS = """
body { margin:0; padding:20px; background:transparent; font-family:'Segoe UI',Arial,sans-serif; }
#events { display:flex; flex-direction:column; gap:12px; }
.netrunner-event { color:#fff; background:rgba(3,12,28,.82); border:1px solid #10d9f4; border-radius:8px; padding:12px 16px; animation:fadeIn .3s ease; }
.netrunner-event strong { color:#10d9f4; margin-right:8px; }
@keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }
"""

DEFAULT_EVENT_JS = """
let lastEventId=0;
function safe(v){const e=document.createElement('span');e.textContent=v??'';return e.innerHTML}
async function updateEvents(){try{const r=await fetch('/api/v1/events?after='+lastEventId,{cache:'no-store'});if(!r.ok)return;for(const event of await r.json()){lastEventId=Math.max(lastEventId,Number(event.id)||0);const data=event.data||{}, node=document.createElement('div');node.className='netrunner-event';node.innerHTML='<strong>'+safe(data.title||event.type||'Evento')+'</strong><span>'+safe(data.message||data.text||'')+'</span>';document.querySelector('#events').prepend(node)}while(document.querySelector('#events').children.length>30)document.querySelector('#events').lastElementChild.remove()}catch(_){}}
updateEvents();setInterval(updateEvents,1000);
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

{{ preview_css|safe }}

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

    preview_css = """
    html, body {
        background-color: #061126 !important;
        background-image:
            linear-gradient(45deg, #08182f 25%, transparent 25%),
            linear-gradient(-45deg, #08182f 25%, transparent 25%),
            linear-gradient(45deg, transparent 75%, #08182f 75%),
            linear-gradient(-45deg, transparent 75%, #08182f 75%) !important;
        background-size: 20px 20px !important;
        background-position: 0 0, 0 10px, 10px -10px, -10px 0 !important;
    }
    """ if request.args.get("preview") else ""

    return render_template_string(

        OVERLAY_TEMPLATE,

        html=LIVE_HTML,

        css=LIVE_CSS,

        js=LIVE_JS,

        preview_css=preview_css
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


@app.route("/events")
def events_overlay():
    # O mesmo caminho serve como fonte de navegador e como API de polling:
    # quando `after` é informado, devolvemos somente eventos novos.
    if "after" in request.args:
        after = request.args.get("after", default=0, type=int)
        with CHAT_LOCK:
            items = [item.copy() for item in EVENT_MESSAGES if item.get("id", 0) > after]
        response = jsonify(items)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response
    controller = DASHBOARD_CONTROLLER
    source = getattr(controller, "event_overlay", None) if controller else None
    source = source or {"html": "<div id=\"events\"></div>", "css": LIVE_CSS, "js": LIVE_JS}
    return render_template_string(OVERLAY_TEMPLATE, html=source["html"], css=source["css"], js=source["js"], preview_css="" if not request.args.get("preview") else "")


@app.route("/api/v1")
def api_info():
    return jsonify({"name": "Netrunner Pulse API", "version": "1", "endpoints": {"chat": "/api/v1/chat", "events": "/api/v1/events"}})


@app.route("/api/v1/chat")
def api_chat_v1():
    return chat()


@app.route("/api/v1/events")
def api_events_v1():
    after = request.args.get("after", default=0, type=int)
    with CHAT_LOCK:
        items = [item.copy() for item in EVENT_MESSAGES if item.get("id", 0) > after]
    response = jsonify(items)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/dashboard")
def dashboard():
    return send_file(resource_path("ui/dashboard.html"))


@app.route("/assets/<path:filename>")
def dashboard_asset(filename):
    return send_from_directory(resource_path("assets"), filename)


@app.route("/api/state")
def dashboard_state():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"error": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.snapshot())


@app.route("/api/platforms")
def dashboard_platforms():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"error": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.platform_registry())


@app.route("/api/v1/templates")
def dashboard_templates():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"error": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.overlay_templates())


@app.route("/api/overlays", methods=["GET", "POST"])
def dashboard_overlay_library():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    payload = request.get_json(silent=True) or {}
    target = request.args.get("target") or payload.get("target", "chat")
    if request.method == "GET":
        return jsonify({"target": target, "items": DASHBOARD_CONTROLLER.list_saved_overlays(target)})
    result = DASHBOARD_CONTROLLER.save_overlay_named(target, payload.get("name"), {key: str(payload.get(key) or "") for key in ("html", "css", "js")})
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/overlays/load", methods=["POST"])
def dashboard_overlay_library_load():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.load_overlay_named(payload.get("target", "chat"), payload.get("name", ""))
    return jsonify(result), 200 if result.get("ok") else 404


@app.route("/api/v1/moderation", methods=["POST"])
def dashboard_moderation():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    result = DASHBOARD_CONTROLLER.moderate(request.get_json(silent=True) or {})
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/capture", methods=["POST"])
def dashboard_start_capture():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.start_capture(payload.get("channels", {}))
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/channels", methods=["POST"])
def dashboard_save_channels():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.save_channels(payload.get("channels", {}))
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/capture/stop", methods=["POST"])
def dashboard_stop_capture():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.stop_capture())


@app.route("/api/overlay", methods=["GET", "POST"])
def dashboard_overlay_source():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    if request.method == "POST":
        result = DASHBOARD_CONTROLLER.apply_overlay(request.get_json(silent=True) or {})
        return jsonify(result), 200 if result.get("ok") else 400
    return jsonify(DASHBOARD_CONTROLLER.overlay_source())


@app.route("/api/shutdown", methods=["POST"])
def dashboard_shutdown():
    if DASHBOARD_CONTROLLER is not None:
        DASHBOARD_CONTROLLER.shutdown()
    return jsonify({"ok": True})


# ==========================================
# FLASK THREAD
# ==========================================

def run_flask():
    serve(
        app,
        host="127.0.0.1",
        port=5000,
        threads=8,
        ident=None,
    )


