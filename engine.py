import os
import sys
import threading
import time
from functools import wraps
from urllib.parse import parse_qs, urlsplit

from flask import Flask, jsonify, make_response, render_template_string, request, send_file, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from waitress import serve

from core.payments import PaymentError, normalize_pix, normalize_stripe, verify_pix_signature, verify_stripe_signature
from core.security import SecurityManager

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
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024


CHAT_MESSAGES = []
EVENT_MESSAGES = []

MAX_MESSAGES = 500

CHAT_LOCK = threading.Lock()

MESSAGE_SEQUENCE = int(time.time() * 1000) * 1000
EVENT_SEQUENCE = int(time.time() * 1000) * 1000

DASHBOARD_CONTROLLER = None
REALTIME_GATEWAY = None
SECURITY_MANAGER = None


def set_dashboard_controller(controller):
    global DASHBOARD_CONTROLLER, SECURITY_MANAGER
    DASHBOARD_CONTROLLER = controller
    if controller is None:
        SECURITY_MANAGER = None
        return
    security_path = os.path.join(os.path.dirname(controller.overlay_config_path), "security.json")
    SECURITY_MANAGER = SecurityManager(security_path)


def ensure_security_manager(config_path=None):
    """Load the same persisted capability file before a child server starts."""
    global SECURITY_MANAGER
    if SECURITY_MANAGER is None:
        if config_path is None:
            overlay_override = os.environ.get("NETRUNNER_OVERLAY_CONFIG")
            if overlay_override:
                config_path = os.path.join(os.path.dirname(os.path.abspath(overlay_override)), "security.json")
            else:
                base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
                config_path = os.path.join(base_dir, "NetrunnerOverlay", "security.json")
        SECURITY_MANAGER = SecurityManager(config_path)
    return SECURITY_MANAGER


def set_realtime_gateway(gateway):
    global REALTIME_GATEWAY
    REALTIME_GATEWAY = gateway


def admin_token():
    return SECURITY_MANAGER.admin_token() if SECURITY_MANAGER is not None else ""


def dashboard_url():
    if SECURITY_MANAGER is None:
        return "http://127.0.0.1:5000/dashboard"
    return SECURITY_MANAGER.admin_access_url("http://127.0.0.1:5000/dashboard")


def overlay_url(kind):
    base = "http://127.0.0.1:5000/events" if kind == "events" else "http://127.0.0.1:5000/overlay"
    return SECURITY_MANAGER.overlay_url(kind, base) if SECURITY_MANAGER is not None else base


def authorize_overlay_path(topic, path):
    if SECURITY_MANAGER is None:
        return False
    kind = "events" if str(urlsplit(str(path)).path).rstrip("/").endswith("/events") else "chat"
    token = parse_qs(urlsplit(str(path)).query, keep_blank_values=True).get("token", [])
    return SECURITY_MANAGER.authenticate_overlay_token(kind, token)


def _admin_denied():
    response = jsonify({"ok": False, "message": "Autenticação administrativa necessária."})
    response.status_code = 401
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if SECURITY_MANAGER is None or not SECURITY_MANAGER.authenticate_admin(request):
            return _admin_denied()
        return view(*args, **kwargs)
    return wrapped


def _overlay_denied():
    return jsonify({"ok": False, "message": "Token do overlay ausente, inválido ou revogado."}), 401


def overlay_required(kind, view=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if SECURITY_MANAGER is None or not SECURITY_MANAGER.authenticate_overlay(kind, request):
                return _overlay_denied()
            return view(*args, **kwargs)
        return wrapped
    return decorator(view) if view is not None else decorator


def _any_overlay_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if SECURITY_MANAGER is None or not SECURITY_MANAGER.authenticate_any_overlay(request):
            return _overlay_denied()
        return view(*args, **kwargs)
    return wrapped


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify({"ok": False, "message": "A requisição excede o limite de 40 MB."}), 413


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.path.startswith("/api/") or request.path in {"/", "/overlay", "/events", "/dashboard"}:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def publish_realtime(topic, payload):
    gateway = REALTIME_GATEWAY
    if gateway is not None:
        gateway.publish(topic, payload)


def realtime_history(topic, after_id=0):
    """Return the in-process source of truth used to recover an overlay reload."""
    source = EVENT_MESSAGES if topic == "events" else CHAT_MESSAGES
    with CHAT_LOCK:
        return [item.copy() for item in source if item.get("id", 0) > after_id]


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
const overlayToken = new URLSearchParams(window.location.search).get("token") || document.querySelector('meta[name="netrunner-overlay-token"]')?.content || "";
function overlayRequest(path) {
    const url = new URL(path, window.location.href);
    if (overlayToken) url.searchParams.set("token", overlayToken);
    return url.toString();
}

let updateInProgress = false;
let realtimeConnected = false;
let realtimeSocket = null;
let realtimeReconnectTimer = null;
let realtimeReconnectDelay = 1000;


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


function removeChatMessage(messageId) {
    const targetId = String(messageId);
    document.querySelectorAll("#log [data-id]").forEach(element => {
        if (String(element.dataset.id) === targetId) {
            element.remove();
        }
    });
}

function handleChatItem(item) {
    const messageId = Number(item?.id);
    if (!Number.isFinite(messageId)) {
        return;
    }
    if (item.type === "message_delete") {
        removeChatMessage(item.messageId);
    } else {
        addChatMessage(item.user, item.message, item.platform, messageId);
    }
    lastMessageId = Math.max(lastMessageId, messageId);
}


async function updateChat() {

    if (realtimeConnected) {
        return;
    }

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
            overlayRequest(`/chat?after=${lastMessageId}&t=${Date.now()}`),
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

            handleChatItem(msg);
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

function connectRealtimeChat() {
    if (!window.WebSocket) return;
    try {
        const scheme = window.location.protocol === "https:" ? "wss" : "ws";
        const socket = new WebSocket(`${scheme}://${window.location.hostname}:5001/ws/chat?after=${encodeURIComponent(lastMessageId)}&token=${encodeURIComponent(overlayToken)}`);
        realtimeSocket = socket;
        socket.onopen = () => { realtimeConnected = true; realtimeReconnectDelay = 1000; };
        socket.onmessage = message => {
            try {
                const item = JSON.parse(message.data);
                if (item.type === "hello") return;
                const messageId = Number(item.id);
                if (!Number.isFinite(messageId) || messageId <= lastMessageId) return;
                handleChatItem(item);
            } catch (_) {}
        };
        socket.onclose = () => {
            if (realtimeSocket !== socket) return;
            realtimeConnected = false;
            realtimeSocket = null;
            clearTimeout(realtimeReconnectTimer);
            const delay = realtimeReconnectDelay;
            realtimeReconnectDelay = Math.min(realtimeReconnectDelay * 2, 30000);
            realtimeReconnectTimer = setTimeout(connectRealtimeChat, delay);
        };
    } catch (_) {
        realtimeConnected = false;
        clearTimeout(realtimeReconnectTimer);
        const delay = realtimeReconnectDelay;
        realtimeReconnectDelay = Math.min(realtimeReconnectDelay * 2, 30000);
        realtimeReconnectTimer = setTimeout(connectRealtimeChat, delay);
    }
}

connectRealtimeChat();
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
.netrunner-event-asset { display:block; max-width:180px; max-height:120px; object-fit:contain; margin-bottom:8px; border-radius:6px; }
.netrunner-audio-unlock { position:fixed; left:12px; bottom:12px; z-index:9999; color:#fff; background:#07152aee; border:1px solid #10d9f4; border-radius:6px; padding:8px 12px; font:12px Arial,sans-serif; cursor:pointer; }
.netrunner-event.is-leaving { animation:fadeOut .25s ease forwards; }
.netrunner-event strong { color:#10d9f4; margin-right:8px; }
@keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }
@keyframes fadeOut { from{opacity:1;transform:none} to{opacity:0;transform:translateY(-8px)} }
"""

DEFAULT_EVENT_JS = """
let lastEventId=0;
const overlayToken=new URLSearchParams(window.location.search).get('token')||document.querySelector('meta[name="netrunner-overlay-token"]')?.content||'';
function overlayRequest(path){const url=new URL(path,window.location.href);if(overlayToken)url.searchParams.set('token',overlayToken);return url.toString()}
let realtimeEventsConnected=false;
let realtimeEventsSocket=null;
let realtimeEventsReconnectTimer=null;
let realtimeEventsReconnectDelay=1000;
function safe(v){const e=document.createElement('span');e.textContent=v??'';return e.innerHTML}
class AlertQueue {
  constructor(root){this.root=root;this.queue=[];this.isShowing=false;this.maxItems=30;this.cooldowns=new Map()}
  addToQueue(event){const data=event.data||{};const cooldownMs=Math.max(0,Number(data.cooldownMs||0));const cooldownKey=String(data.cooldownKey||event.type||'event');const now=Date.now();if(cooldownMs&&now<(this.cooldowns.get(cooldownKey)||0))return;if(cooldownMs)this.cooldowns.set(cooldownKey,now+cooldownMs);const priority=Number(data.priority??({donation:100,superchat:100,raid:80,bits:60,subscription:50,member:50,gift:30}[event.type]||10));if(data.assetUrl)preloadAsset(data.assetUrl,data.assetType||'image');if(data.soundUrl)preloadAsset(data.soundUrl,'audio');event._queuePriority=Number.isFinite(priority)?priority:10;this.queue.push(event);this.queue.sort((a,b)=>(b._queuePriority-a._queuePriority)||((Number(a.id)||0)-(Number(b.id)||0)));this.processNext()}
  async processNext(){
    if(this.isShowing||this.queue.length===0)return;
    this.isShowing=true;
    const event=this.queue.shift();
    try{await this.renderAlert(event)}finally{this.isShowing=false;this.processNext()}
  }
  renderAlert(event){
    return new Promise(resolve=>{
      const data=event.data||{}, node=document.createElement('div');
      node.className='netrunner-event event-'+safe(event.type||'system');
      node.dataset.eventId=String(event.id||'');
      node.innerHTML='<strong>'+safe(data.title||event.type||'Evento')+'</strong><span>'+safe(data.message||data.text||'')+'</span>';
      if(data.assetUrl){const visual=document.createElement(data.assetType==='video'?'video':'img');visual.src=data.assetUrl;visual.alt='';visual.className='netrunner-event-asset';if(data.assetType==='video'){visual.autoplay=true;visual.muted=true;visual.playsInline=true}node.prepend(visual)}
      if(data.soundUrl)audioManager.play(data.soundUrl,data.volume);
      const ttsEnabled=data.tts===true||data.tts==='true'||(window.NetrunnerTTS&&window.NetrunnerTTS.enabled);if(ttsEnabled)speakAlert(data.ttsText||data.message||data.text||data.title,{rate:data.ttsRate,volume:data.ttsVolume});
      this.root.prepend(node);
      while(this.root.children.length>this.maxItems)this.root.lastElementChild.remove();
      const duration=Math.max(500,Number(data.duration||data.durationMs||8000));
      setTimeout(()=>{node.classList.add('is-leaving');setTimeout(()=>{node.remove();resolve()},250)},duration);
    })
  }
}
const assetPreloadCache=new Map();
function preloadAsset(url,kind='image'){
  if(!url)return Promise.resolve(null);
  if(assetPreloadCache.has(url))return assetPreloadCache.get(url).promise;
  const node=kind==='audio'?new Audio():document.createElement(kind==='video'?'video':'img');
  node.preload='auto';
  node.src=url;
  const promise=new Promise(resolve=>{node.addEventListener('canplaythrough',()=>resolve(node),{once:true});node.addEventListener('load',()=>resolve(node),{once:true});node.addEventListener('error',()=>resolve(null),{once:true})});
  assetPreloadCache.set(url,{node,promise});
  return promise;
}
window.NetrunnerAssets={preload:preloadAsset,cache:assetPreloadCache};
class AudioManager {
  constructor(){this.unlocked=false;this.pending=[];this.cache=new Map();this.unlockButton=null;document.addEventListener('pointerdown',()=>this.unlock(),{passive:true});document.addEventListener('keydown',()=>this.unlock(),{passive:true})}
  showUnlock(){if(this.unlockButton||!document.body)return;const button=document.createElement('button');button.className='netrunner-audio-unlock';button.type='button';button.textContent='Ativar sons';button.addEventListener('click',()=>this.unlock());document.body.appendChild(button);this.unlockButton=button}
  async unlock(){this.unlocked=true;try{const Context=window.AudioContext||window.webkitAudioContext;if(Context&&!this.context)this.context=new Context();if(this.context&&this.context.state==='suspended')await this.context.resume()}catch(_){}if(this.unlockButton){this.unlockButton.remove();this.unlockButton=null}const pending=this.pending.splice(0,10);for(const item of pending)await this.play(item.url,item.volume)}
  async play(url,volume=1){if(!url)return false;if(!this.unlocked){if(this.pending.length<10)this.pending.push({url,volume});this.showUnlock();return false}let audio=this.cache.get(url);if(!audio){audio=new Audio(url);audio.preload='auto';this.cache.set(url,audio)}const level=Number(volume);audio.volume=Number.isFinite(level)?Math.min(1,Math.max(0,level)):1;audio.currentTime=0;try{await audio.play();return true}catch(_){this.unlocked=false;this.showUnlock();return false}}
}
const audioManager=new AudioManager();
function escapeRegExp(value){const special=String.fromCharCode(92)+'^$.*+?()[]{}|';return String(value).split('').map(character=>special.includes(character)?String.fromCharCode(92)+character:character).join('')}
function speechText(text){const config=window.NetrunnerTTS||{};const blocked=Array.isArray(config.blockedWords)?config.blockedWords.filter(Boolean):[];let safeText=String(text||'');for(const word of blocked)safeText=safeText.replace(new RegExp(escapeRegExp(word),'gi'),'');return safeText.replace(new RegExp(String.fromCharCode(92)+'s+','g'),' ').trim()}
function speakAlert(text,options={}){if(!('speechSynthesis' in window)||typeof SpeechSynthesisUtterance==='undefined')return false;const config=window.NetrunnerTTS||{};const safeText=speechText(text);if(!safeText)return false;const utterance=new SpeechSynthesisUtterance(safeText);const rate=Number(options.rate??config.rate??1);const volume=Number(options.volume??config.volume??1);utterance.rate=Number.isFinite(rate)?Math.min(2,Math.max(.5,rate)):1;utterance.volume=Number.isFinite(volume)?Math.min(1,Math.max(0,volume)):1;try{window.speechSynthesis.cancel();window.speechSynthesis.speak(utterance);return true}catch(_){return false}}
window.NetrunnerTTS={enabled:false,blockedWords:[],rate:1,volume:1,speak:speakAlert};
const alertQueue=new AlertQueue(document.querySelector('#events'));
function acceptRealtimeEvent(event){const id=Number(event.id)||0;if(!id||id<=lastEventId)return;lastEventId=id;alertQueue.addToQueue(event)}
function connectRealtimeEvents(){
  if(!window.WebSocket)return;
  try{
    const scheme=window.location.protocol==='https:'?'wss':'ws';
    const socket=new WebSocket(`${scheme}://${window.location.hostname}:5001/ws/events?after=${encodeURIComponent(lastEventId)}&token=${encodeURIComponent(overlayToken)}`);
    realtimeEventsSocket=socket;
    socket.onopen=()=>{realtimeEventsConnected=true;realtimeEventsReconnectDelay=1000};
    socket.onmessage=message=>{try{const event=JSON.parse(message.data);if(event.type!=='hello')acceptRealtimeEvent(event)}catch(_){} };
  socket.onclose=()=>{if(realtimeEventsSocket!==socket)return;realtimeEventsConnected=false;realtimeEventsSocket=null;clearTimeout(realtimeEventsReconnectTimer);const delay=realtimeEventsReconnectDelay;realtimeEventsReconnectDelay=Math.min(realtimeEventsReconnectDelay*2,30000);realtimeEventsReconnectTimer=setTimeout(connectRealtimeEvents,delay)};
  }catch(_){realtimeEventsConnected=false;clearTimeout(realtimeEventsReconnectTimer);const delay=realtimeEventsReconnectDelay;realtimeEventsReconnectDelay=Math.min(realtimeEventsReconnectDelay*2,30000);realtimeEventsReconnectTimer=setTimeout(connectRealtimeEvents,delay)}
}
async function updateEvents(){if(realtimeEventsConnected)return;try{const r=await fetch(overlayRequest('/api/v1/events?after='+lastEventId),{cache:'no-store'});if(!r.ok)return;for(const event of await r.json())acceptRealtimeEvent(event)}catch(_){} }
connectRealtimeEvents();
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
@overlay_required("chat")
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
@overlay_required("chat")
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
@overlay_required("events")
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
    return jsonify({"name": "Netrunner Pulse API", "version": "1", "endpoints": {"chat": "/api/v1/chat", "state": "/api/state", "events": "/api/v1/events", "pixWebhook": "/api/v1/webhooks/pix", "stripeWebhook": "/api/v1/webhooks/stripe"}})


@app.route("/api/v1/chat")
@overlay_required("chat")
def api_chat_v1():
    return chat()


@app.route("/api/v1/events")
@overlay_required("events")
def api_events_v1():
    after = request.args.get("after", default=0, type=int)
    with CHAT_LOCK:
        items = [item.copy() for item in EVENT_MESSAGES if item.get("id", 0) > after]
    response = jsonify(items)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def _payment_webhook(provider, verifier, normalizer, signature_header):
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    secret_name = "NETRUNNER_PIX_WEBHOOK_SECRET" if provider == "pix" else "NETRUNNER_STRIPE_WEBHOOK_SECRET"
    secret = os.environ.get(secret_name, "")
    if not secret:
        return jsonify({"ok": False, "message": f"Webhook {provider} não configurado."}), 503
    raw_body = request.get_data(cache=True)
    if not verifier(raw_body, request.headers.get(signature_header), secret):
        DASHBOARD_CONTROLLER.record_operational_log(f"[PAGAMENTOS] Webhook {provider} recusado: assinatura inválida", "orange")
        return jsonify({"ok": False, "message": "Assinatura do webhook inválida."}), 401
    try:
        payload = request.get_json(silent=False)
    except Exception:
        DASHBOARD_CONTROLLER.record_operational_log(f"[PAGAMENTOS] Webhook {provider} descartado: JSON inválido", "orange")
        return jsonify({"ok": False, "message": "Payload JSON inválido."}), 400
    try:
        donation = normalizer(payload, os.environ.get("NETRUNNER_STREAMER_ID", "local"))
    except PaymentError as error:
        DASHBOARD_CONTROLLER.record_operational_log(f"[PAGAMENTOS] Webhook {provider} descartado: {error}", "orange")
        return jsonify({"ok": False, "message": str(error)}), 400
    result = DASHBOARD_CONTROLLER.confirm_donation(provider, donation)
    return jsonify({
        "ok": result.get("ok", False),
        "accepted": result.get("accepted", False),
        "duplicate": result.get("duplicate", False),
        "message": result.get("message", ""),
    }), 200 if result.get("ok") else 400


@app.route("/api/v1/webhooks/pix", methods=["POST"])
def pix_webhook():
    return _payment_webhook("pix", verify_pix_signature, normalize_pix, "X-Netrunner-Signature")


@app.route("/api/v1/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    return _payment_webhook("stripe", verify_stripe_signature, normalize_stripe, "Stripe-Signature")


@app.route("/dashboard")
def dashboard():
    if SECURITY_MANAGER is None or not SECURITY_MANAGER.authenticate_admin(request, allow_query=True):
        return _admin_denied()
    response = make_response(send_file(resource_path("ui/dashboard.html")))
    if request.args.get("admin"):
        response.set_cookie(
            "netrunner_admin",
            SECURITY_MANAGER.admin_token(),
            httponly=True,
            samesite="Strict",
            max_age=60 * 60 * 12,
        )
    return response


@app.route("/assets/<path:filename>")
def dashboard_asset(filename):
    return send_from_directory(resource_path("assets"), filename)


@app.route("/api/state")
@admin_required
def dashboard_state():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"error": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.snapshot())


@app.route("/api/platforms")
@admin_required
def dashboard_platforms():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"error": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.platform_registry())


@app.route("/api/security/tokens", methods=["GET", "POST"])
@admin_required
def dashboard_security_tokens():
    if SECURITY_MANAGER is None:
        return jsonify({"ok": False, "message": "Segurança local indisponível."}), 503
    if request.method == "GET":
        return jsonify(SECURITY_MANAGER.snapshot({
            "chat": "http://127.0.0.1:5000/overlay",
            "events": "http://127.0.0.1:5000/events",
        }))
    payload = request.get_json(silent=True) or {}
    kind = str(payload.get("kind") or "").lower()
    action = str(payload.get("action") or "rotate").lower()
    if action == "rotate":
        result = SECURITY_MANAGER.rotate_overlay(kind)
    elif action == "revoke":
        result = SECURITY_MANAGER.revoke_overlay(kind)
    else:
        result = {"ok": False, "message": "Ação de segurança desconhecida."}
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/diagnostics", methods=["GET", "POST"])
@admin_required
def dashboard_diagnostics():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    if request.method == "GET":
        return jsonify(DASHBOARD_CONTROLLER.diagnostics_snapshot())
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.start_diagnostic(payload.get("durationSeconds", 60))
    return jsonify(result), 200 if result.get("ok") else 409


@app.route("/api/v1/templates")
@admin_required
def dashboard_templates():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"error": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.overlay_templates())


@app.route("/api/overlays", methods=["GET", "POST"])
@admin_required
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
@admin_required
def dashboard_overlay_library_load():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.load_overlay_named(payload.get("target", "chat"), payload.get("name", ""))
    return jsonify(result), 200 if result.get("ok") else 404


@app.route("/api/overlays/history")
@admin_required
def dashboard_overlay_history():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    target = request.args.get("target", "chat")
    return jsonify({"ok": True, "target": target, "items": DASHBOARD_CONTROLLER.list_overlay_history(target)})


@app.route("/api/overlays/history/load", methods=["POST"])
@admin_required
def dashboard_overlay_history_load():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.load_overlay_history(payload.get("target", "chat"), payload.get("name", ""))
    return jsonify(result), 200 if result.get("ok") else 404


@app.route("/api/overlays/validate", methods=["POST"])
@admin_required
def dashboard_overlay_validate():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.validate_overlay(request.get_json(silent=True) or {}))


@app.route("/api/assets", methods=["GET", "POST"])
@admin_required
def dashboard_assets():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    if request.method == "GET":
        return jsonify({"ok": True, "items": DASHBOARD_CONTROLLER.list_assets()})
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.save_asset(payload.get("name", ""), payload.get("content", ""))
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/overlay-assets/<path:filename>")
def overlay_asset(filename):
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    return send_from_directory(DASHBOARD_CONTROLLER.asset_library_root, filename, conditional=True)


@app.route("/api/v1/moderation", methods=["POST"])
@admin_required
def dashboard_moderation():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    result = DASHBOARD_CONTROLLER.moderate(request.get_json(silent=True) or {})
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/v1/events/test", methods=["POST"])
@admin_required
def dashboard_test_event():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    result = DASHBOARD_CONTROLLER.test_event(request.get_json(silent=True) or {})
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/capture", methods=["POST"])
@admin_required
def dashboard_start_capture():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.start_capture(payload.get("channels", {}))
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/channels", methods=["POST"])
@admin_required
def dashboard_save_channels():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    payload = request.get_json(silent=True) or {}
    result = DASHBOARD_CONTROLLER.save_channels(payload.get("channels", {}))
    return jsonify(result), 200 if result.get("ok") else 400


@app.route("/api/capture/stop", methods=["POST"])
@admin_required
def dashboard_stop_capture():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    return jsonify(DASHBOARD_CONTROLLER.stop_capture())


@app.route("/api/overlay", methods=["GET", "POST"])
@admin_required
def dashboard_overlay_source():
    if DASHBOARD_CONTROLLER is None:
        return jsonify({"ok": False, "message": "Dashboard indisponível."}), 503
    if request.method == "POST":
        result = DASHBOARD_CONTROLLER.apply_overlay(request.get_json(silent=True) or {})
        return jsonify(result), 200 if result.get("ok") else 400
    return jsonify(DASHBOARD_CONTROLLER.overlay_source())


@app.route("/api/shutdown", methods=["POST"])
@admin_required
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


