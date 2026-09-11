import base64
import json
import os
import queue
import re
import threading
import time
import uuid
from collections import deque
from datetime import datetime

import psutil

import engine
from bots.kick import KickBot
from bots.tiktok import TikTokBot
from bots.twitch import TwitchBot
from bots.youtube import YouTubeBot
from core.chat_schema import normalize_chat_message
from core.donations import DonationLedger
from core.event_schema import normalize_event, normalize_event_type
from core.event_bus import EventBus
from core.platforms import PLATFORM_REGISTRY
from core.sanitization import sanitize_text
from core.version import APP_VERSION


PLATFORMS = {
    "twitch": TwitchBot,
    "youtube": YouTubeBot,
    "tiktok": TikTokBot,
    "kick": KickBot,
}

OVERLAY_CONFIG_ENV = "NETRUNNER_OVERLAY_CONFIG"
CHANNELS_CONFIG_ENV = "NETRUNNER_CHANNELS_CONFIG"
MAX_OVERLAY_SECTION_BYTES = 1024 * 1024
OVERLAY_HISTORY_LIMIT = 20
MAX_ASSET_BYTES = 25 * 1024 * 1024
ASSET_MIME_TYPES = {
    ".png": "image/png",
    ".gif": "image/gif",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}
EVENT_DEDUPE_TTL_SECONDS = 120
PAYMENT_SOURCES = {"pix", "stripe"}
DIAGNOSTIC_MIN_SECONDS = 5
DIAGNOSTIC_MAX_SECONDS = 3600


def default_overlay_config_path():
    override = os.environ.get(OVERLAY_CONFIG_ENV)
    if override:
        return os.path.abspath(override)
    base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base_dir, "NetrunnerOverlay", "overlay.json")


def default_channels_config_path():
    override = os.environ.get(CHANNELS_CONFIG_ENV)
    if override:
        return os.path.abspath(override)
    base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base_dir, "NetrunnerOverlay", "channels.json")


def normalize_channel_input(value):
    """Normalize identifiers without changing URL punctuation or @ handles."""
    return re.sub(r"\s+", "", str(value or "").strip())


class WebDashboardController:
    """Thread-safe bridge between the web dashboard and the capture workers."""

    def __init__(self, overlay_config_path=None, channels_config_path=None):
        self.events = queue.Queue(maxsize=2000)
        self.lock = threading.RLock()
        self.bots = []
        self.messages = deque(maxlen=50)
        self.events_feed = deque(maxlen=80)
        self.event_bus = EventBus(max_events=200)
        self._event_dedup = {}
        self.ignored_users = set()
        self.activity = deque(maxlen=80)
        self.logs = deque(maxlen=200)
        self.counts = {platform: 0 for platform in PLATFORMS}
        self.connected = {platform: False for platform in PLATFORMS}
        self.status_labels = {platform: "Desconectado" for platform in PLATFORMS}
        self.last_activity = {platform: None for platform in PLATFORMS}
        self.channels = {platform: "" for platform in PLATFORMS}
        self.is_capturing = False
        self.is_stopping = False
        self.closed = False
        self.session_started = None
        self.diagnostic_lock = threading.RLock()
        self.diagnostic = {
            "status": "idle",
            "requestedSeconds": 0,
            "elapsedSeconds": 0,
            "startedAt": None,
            "finishedAt": None,
            "message": "Nenhum teste de resiliência executado.",
            "checks": {
                "samples": 0,
                "maxQueueDepth": 0,
                "queueErrors": 0,
                "gatewayDownSamples": 0,
            },
            "lastSample": None,
        }
        self._diagnostic_thread = None
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent()
        self.overlay_config_path = overlay_config_path or default_overlay_config_path()
        self.overlay_library_root = os.path.join(os.path.dirname(self.overlay_config_path), "overlays")
        self.overlay_history_root = os.path.join(os.path.dirname(self.overlay_config_path), "overlay-history")
        self.asset_library_root = os.path.join(os.path.dirname(self.overlay_config_path), "assets")
        self.donation_ledger = DonationLedger(
            os.path.join(os.path.dirname(self.overlay_config_path), "donations.json"),
            streamer_id=os.environ.get("NETRUNNER_STREAMER_ID", "local"),
        )
        self.channels_config_path = channels_config_path or default_channels_config_path()
        self.overlay_is_saved = False
        self.event_overlay = {
            "html": engine.DEFAULT_EVENT_HTML,
            "css": engine.DEFAULT_EVENT_CSS,
            "js": engine.DEFAULT_EVENT_JS,
        }
        self._load_overlay_settings()
        self._load_channels()
        self._add_activity(f"Aplicação v{APP_VERSION} iniciada", "cyan")
        self._event_thread = threading.Thread(
            target=self._event_loop,
            name="DashboardEvents",
            daemon=True,
        )
        self._event_thread.start()

    def _event_loop(self):
        while not self.closed:
            try:
                event = self.events.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                kind = event[0]
                if kind == "message":
                    self._receive_message(*event[1:])
                elif kind == "event":
                    self._receive_event(*event[1:])
                elif kind == "status":
                    self._receive_status(*event[1:])
                elif kind == "finished":
                    self._bot_finished(*event[1:])
                else:
                    self.record_operational_log(f"[EVENTOS] Registro descartado: tipo desconhecido {kind!r}", "orange")
            except Exception as error:
                self.record_operational_log(f"[EVENTOS] Falha ao processar registro: {error}", "orange")

    def _enqueue_capture_event(self, payload):
        try:
            self.events.put_nowait(payload)
        except queue.Full:
            self.record_operational_log("[EVENTOS] Registro descartado: fila de captura cheia.", "orange")

    def start_capture(self, channels):
        with self.lock:
            if self.is_capturing or self.is_stopping:
                return {"ok": False, "message": "A captura já está ativa."}

            clean = {
                platform: normalize_channel_input((channels or {}).get(platform, ""))
                for platform in PLATFORMS
            }
            configs = [
                (platform, PLATFORMS[platform], channel)
                for platform, channel in clean.items()
                if channel
            ]
            if not configs:
                return {"ok": False, "message": "Informe ao menos um canal."}

            self.channels.update(clean)
            self._persist_channels(clean)
            self.bots = [bot for bot in self.bots if bot.isRunning()]
            running_types = {type(bot) for bot in self.bots}
            started = 0
            for platform, bot_class, channel in configs:
                if bot_class in running_types:
                    continue
                bot = bot_class(channel)
                bot.new_message.connect(
                    lambda user, message, source:
                    self._enqueue_capture_event(("message", user, message, source))
                )
                if hasattr(bot, "new_event"):
                    bot.new_event.connect(
                        lambda event, source=platform:
                        self._enqueue_capture_event(("event", event, source))
                    )
                bot.status_update.connect(
                    lambda status, source=platform:
                    self._enqueue_capture_event(("status", source, status))
                )
                bot.finished.connect(
                    lambda current=bot, source=platform:
                    self._enqueue_capture_event(("finished", source, current))
                )
                self.bots.append(bot)
                self._set_platform(platform, False, "Conectando...")
                bot.start()
                started += 1

            if started:
                self.is_capturing = True
                self.session_started = time.monotonic()
                self._add_activity("Captura iniciada", "green")
            return {"ok": bool(started), "message": "Captura iniciada." if started else "Nenhuma nova captura iniciada."}

    def save_channels(self, channels):
        with self.lock:
            clean = {
                platform: normalize_channel_input((channels or {}).get(platform, ""))
                for platform in PLATFORMS
            }
            self.channels.update(clean)
            self._persist_channels(clean)
        return {"ok": True, "message": "Canais salvos."}

    def platform_registry(self):
        return {key: dict(value) for key, value in PLATFORM_REGISTRY.items()}

    def overlay_templates(self):
        chat_minimal_css = """
body { margin:0; padding:16px; background:transparent; font-family:Arial,sans-serif; }
#log { display:flex; flex-direction:column; gap:8px; }
.chat-message { width:fit-content; max-width:90%; padding:8px 12px; color:#f5f7ff; background:rgba(5,12,27,.82); border-left:3px solid #10d9f4; border-radius:4px; }
.name { color:#10d9f4; font-weight:700; margin-right:5px; }
.platform-icon { width:18px; height:18px; object-fit:contain; vertical-align:-4px; margin-right:5px; }
.colon { color:#7feaff; margin-right:5px; }
.message { color:#fff; }
"""
        events_minimal_css = """
body { margin:0; padding:16px; background:transparent; font-family:Arial,sans-serif; }
#events { display:flex; flex-direction:column; gap:8px; }
.netrunner-event { color:#f5f7ff; background:rgba(5,12,27,.86); border-left:3px solid #10d9f4; border-radius:4px; padding:10px 14px; }
.netrunner-event strong { color:#10d9f4; margin-right:8px; }
.netrunner-event.is-leaving { opacity:0; transition:opacity .25s ease; }
"""
        return {
            "chat": {"name": "Chat compacto", "target": "chat", "html": "<div id=\"log\"></div>", "css": engine.DEFAULT_LIVE_CSS, "js": engine.DEFAULT_LIVE_JS},
            "events": {"name": "Alertas de eventos", "target": "events", "html": engine.DEFAULT_EVENT_HTML, "css": engine.DEFAULT_EVENT_CSS, "js": engine.DEFAULT_EVENT_JS},
            "chat-minimal": {"name": "Chat minimalista", "target": "chat", "html": "<div id=\"log\"></div>", "css": chat_minimal_css, "js": engine.DEFAULT_LIVE_JS},
            "events-minimal": {"name": "Alertas minimalistas", "target": "events", "html": engine.DEFAULT_EVENT_HTML, "css": events_minimal_css, "js": engine.DEFAULT_EVENT_JS},
        }

    def list_saved_overlays(self, target="chat"):
        folder = os.path.join(self.overlay_library_root, "events" if target == "events" else "chat")
        if not os.path.isdir(folder):
            return []
        return sorted(name[:-5] for name in os.listdir(folder) if name.endswith(".json"))

    def save_overlay_named(self, target, name, source):
        target = "events" if target == "events" else "chat"
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(name or "overlay")).strip("-") or "overlay"
        folder = os.path.join(self.overlay_library_root, target)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, safe + ".json")
        self._save_json_file(path, {"version": 1, "target": target, **source})
        return {"ok": True, "name": safe, "message": "Overlay salvo na biblioteca."}

    def save_overlay_history(self, target, source):
        target = "events" if target == "events" else "chat"
        folder = os.path.join(self.overlay_history_root, target)
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        name = f"{stamp}-{uuid.uuid4().hex[:8]}"
        path = os.path.join(folder, name + ".json")
        self._save_json_file(
            path,
            {"version": 2, "target": target, "createdAt": datetime.now().isoformat(timespec="seconds"), **source},
        )
        files = sorted(
            (entry for entry in os.listdir(folder) if entry.endswith(".json")),
            reverse=True,
        )
        for old_name in files[OVERLAY_HISTORY_LIMIT:]:
            try:
                os.remove(os.path.join(folder, old_name))
            except OSError:
                pass
        return name

    def list_overlay_history(self, target="chat"):
        target = "events" if target == "events" else "chat"
        folder = os.path.join(self.overlay_history_root, target)
        if not os.path.isdir(folder):
            return []
        return sorted(
            (name[:-5] for name in os.listdir(folder) if name.endswith(".json")),
            reverse=True,
        )

    def load_overlay_history(self, target, name):
        target = "events" if target == "events" else "chat"
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(name or "")).strip("-")
        path = os.path.join(self.overlay_history_root, target, safe + ".json")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return {
                "ok": True,
                **{key: str(data.get(key) or "") for key in ("html", "css", "js")},
                "target": target,
                "createdAt": data.get("createdAt", ""),
            }
        except (OSError, ValueError, json.JSONDecodeError):
            return {"ok": False, "message": "Versão do histórico não encontrada."}

    @staticmethod
    def _safe_asset_name(name):
        original = os.path.basename(str(name or "").strip())
        stem, extension = os.path.splitext(original)
        extension = extension.lower()
        if extension not in ASSET_MIME_TYPES:
            return "", ""
        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-") or "asset"
        return safe_stem + extension, ASSET_MIME_TYPES[extension]

    def save_asset(self, name, encoded_content):
        safe_name, mime_type = self._safe_asset_name(name)
        if not safe_name:
            return {"ok": False, "message": "Formato de asset não permitido. Use PNG, GIF, WebM, MP3, WAV ou OGG."}
        if not isinstance(encoded_content, str):
            return {"ok": False, "message": "Conteúdo do asset inválido."}
        if len(encoded_content) > int(MAX_ASSET_BYTES * 1.4):
            return {"ok": False, "message": "O asset excede o limite de 25 MB."}
        try:
            content = base64.b64decode(encoded_content, validate=True)
        except (ValueError, TypeError):
            return {"ok": False, "message": "Conteúdo do asset não está em Base64 válido."}
        if len(content) > MAX_ASSET_BYTES:
            return {"ok": False, "message": "O asset excede o limite de 25 MB."}
        os.makedirs(self.asset_library_root, exist_ok=True)
        path = os.path.join(self.asset_library_root, safe_name)
        temporary = path + ".tmp"
        try:
            with open(temporary, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as error:
            try:
                os.remove(temporary)
            except OSError:
                pass
            self._log(f"[ASSETS] Falha ao salvar {safe_name}: {error}", "youtube", activity=False)
            return {"ok": False, "message": "Não foi possível salvar o asset localmente."}
        return {
            "ok": True,
            "name": safe_name,
            "mimeType": mime_type,
            "size": len(content),
            "url": f"/overlay-assets/{safe_name}",
            "message": "Asset salvo na biblioteca local.",
        }

    def list_assets(self):
        if not os.path.isdir(self.asset_library_root):
            return []
        assets = []
        for name in sorted(os.listdir(self.asset_library_root)):
            path = os.path.join(self.asset_library_root, name)
            extension = os.path.splitext(name)[1].lower()
            if not os.path.isfile(path) or extension not in ASSET_MIME_TYPES:
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            assets.append({
                "name": name,
                "mimeType": ASSET_MIME_TYPES[extension],
                "size": size,
                "url": f"/overlay-assets/{name}",
            })
        return assets

    @staticmethod
    def _delimiter_errors(source, label):
        pairs = {"{": "}", "[": "]", "(": ")"}
        closing = set(pairs.values())
        stack = []
        quote = None
        escaped = False
        line_comment = False
        block_comment = False
        index = 0
        while index < len(source):
            char = source[index]
            next_char = source[index + 1] if index + 1 < len(source) else ""
            if line_comment:
                if char == "\n":
                    line_comment = False
                index += 1
                continue
            if block_comment:
                if char == "*" and next_char == "/":
                    block_comment = False
                    index += 2
                    continue
                index += 1
                continue
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue
            if char in "'\"`":
                quote = char
            elif char == "/" and next_char == "/":
                line_comment = True
                index += 2
                continue
            elif char == "/" and next_char == "*":
                block_comment = True
                index += 2
                continue
            elif char in pairs:
                stack.append(char)
            elif char in closing:
                if not stack or pairs[stack[-1]] != char:
                    return f"{label}: delimitador inesperado na posição {index}."
                stack.pop()
            index += 1
        if quote:
            return f"{label}: string não fechada."
        if block_comment:
            return f"{label}: comentário não fechado."
        if stack:
            return f"{label}: delimitador '{stack[-1]}' não fechado."
        return None

    def validate_overlay(self, payload=None):
        payload = payload or {}
        source = {key: str(payload.get(key) or "") for key in ("html", "css", "js")}
        errors = []
        oversized = [
            name for name, value in source.items()
            if len(value.encode("utf-8")) > MAX_OVERLAY_SECTION_BYTES
        ]
        if oversized:
            errors.append("A personalização excede o limite de 1 MB em: " + ", ".join(oversized) + ".")
        for name, value in source.items():
            if "\x00" in value:
                errors.append(f"{name.upper()}: caractere inválido encontrado.")
        for label, value in (("CSS", source["css"]), ("JS", source["js"])):
            delimiter_error = self._delimiter_errors(value, label)
            if delimiter_error:
                errors.append(delimiter_error)
        return {"ok": True, "valid": not errors, "errors": errors, "warnings": []}

    def load_overlay_named(self, target, name):
        target = "events" if target == "events" else "chat"
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(name or "")).strip("-")
        path = os.path.join(self.overlay_library_root, target, safe + ".json")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return {"ok": True, **{key: str(data.get(key) or "") for key in ("html", "css", "js")}, "target": target}
        except (OSError, ValueError, json.JSONDecodeError):
            return {"ok": False, "message": "Overlay salvo não encontrado."}

    @staticmethod
    def _save_json_file(path, data):
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)

    def moderate(self, payload):
        payload = payload or {}
        action = str(payload.get("action") or "").lower()
        if action == "ignore_user":
            user_id = str(payload.get("userId") or payload.get("user") or "").strip()
            if user_id:
                self.ignored_users.add(user_id)
            return {"ok": True, "message": "Usuário ignorado."}
        if action == "allow_user":
            self.ignored_users.discard(str(payload.get("userId") or payload.get("user") or ""))
            return {"ok": True, "message": "Usuário liberado."}
        if action in {"message_delete", "delete_message"}:
            try:
                message_id = int(payload.get("messageId"))
            except (TypeError, ValueError):
                return {"ok": False, "message": "Informe um ID de mensagem válido."}
            if message_id <= 0:
                return {"ok": False, "message": "Informe um ID de mensagem válido."}
            removed = self._remove_chat_messages(lambda message: message.get("id") == message_id)
            if not removed:
                return {"ok": False, "message": "Mensagem não encontrada."}
            return {"ok": True, "message": "Mensagem removida."}
        if action in {"user_messages_delete", "delete_user"}:
            user_id = str(payload.get("userId") or payload.get("user") or "")
            if not user_id:
                return {"ok": False, "message": "Informe o usuário da mensagem."}
            removed = self._remove_chat_messages(
                lambda message: str(message.get("userId") or message.get("user")) == user_id
            )
            return {
                "ok": True,
                "message": "Mensagens do usuário removidas." if removed else "Nenhuma mensagem do usuário encontrada.",
            }
        return {"ok": False, "message": "Ação de moderação desconhecida."}

    def _remove_chat_messages(self, predicate):
        """Remove dashboard/history messages and publish replayable tombstones."""
        with self.lock:
            removed = [message for message in self.messages if predicate(message)]
            if not removed:
                return []
            removed_ids = {int(message["id"]) for message in removed if message.get("id")}
            self.messages = deque(
                (message for message in self.messages if message.get("id") not in removed_ids),
                maxlen=50,
            )
            with engine.CHAT_LOCK:
                engine.CHAT_MESSAGES[:] = [
                    message for message in engine.CHAT_MESSAGES
                    if message.get("id") not in removed_ids
                ]
                tombstones = []
                for message_id in sorted(removed_ids):
                    engine.MESSAGE_SEQUENCE += 1
                    tombstone = {
                        "id": engine.MESSAGE_SEQUENCE,
                        "type": "message_delete",
                        "messageId": message_id,
                    }
                    engine.CHAT_MESSAGES.append(tombstone)
                    tombstones.append(tombstone)
                del engine.CHAT_MESSAGES[:-engine.MAX_MESSAGES]
        for tombstone in tombstones:
            engine.publish_realtime("chat", tombstone)
        return removed

    def test_event(self, payload=None):
        payload = payload or {}
        platform = str(payload.get("platform") or "tiktok").lower()
        if platform not in PLATFORMS:
            platform = "tiktok"
        event_type = normalize_event_type(payload.get("type") or "gift")
        defaults = {
            "follow": ("Novo seguidor", "Netrunner Test começou a seguir", {"count": 1}),
            "sub": ("Nova inscrição", "Netrunner Test se inscreveu", {"count": 1, "duration": 5000}),
            "gift": ("Presente recebido", "Netrunner Test enviou uma Rose", {"giftName": "Rose", "count": 1}),
            "donation": ("Doação recebida", "Netrunner Test enviou uma doação", {"amount": "10"}),
            "raid": ("Raid recebido", "Netrunner Test chegou com uma raid", {"count": 5}),
            "like": ("Curtida recebida", "Netrunner Test curtiu a live", {"count": 1}),
            "share": ("Live compartilhada", "Netrunner Test compartilhou a live", {"count": 1}),
            "bits": ("Bits recebidos", "Netrunner Test enviou Bits", {"amount": "100"}),
            "superchat": ("Super Chat recebido", "Netrunner Test enviou um Super Chat", {"amount": "R$ 10,00"}),
            "membership": ("Membro novo", "Netrunner Test entrou como membro", {"count": 1}),
        }
        default_title, default_message, extra_data = defaults.get(
            event_type,
            ("Evento de teste", "Evento de teste recebido", {}),
        )
        self._receive_event({
            "type": event_type,
            "data": {
                "eventId": f"test-{uuid.uuid4().hex}",
                "title": str(payload.get("title") or default_title),
                "message": str(payload.get("message") or default_message),
                "user": "Netrunner Test",
                "displayName": "Netrunner Test",
                "duration": int(payload.get("duration") or 5000),
                **extra_data,
            },
        }, platform)
        return {"ok": True, "message": "Evento de teste enviado."}

    def stop_capture(self):
        with self.lock:
            if self.is_stopping:
                return {"ok": False, "message": "A captura já está encerrando."}
            self.is_stopping = True
            self.is_capturing = False
            bots = list(self.bots)
        for bot in bots:
            bot.requestInterruption()

        # Do not allow a new capture to start while a platform client is still
        # unwinding its network loop.  This is especially important for
        # TikTokLive, whose async client can otherwise overlap with the next
        # connection after a stop/reconnect click.
        wait_results = [bot.wait(5000) for bot in bots]
        stopped = all(wait_results)
        with self.lock:
            self.bots = [bot for bot in self.bots if bot.isRunning()]
            for platform in PLATFORMS:
                self._set_platform(platform, False, "Desconectado")
            if stopped:
                self._add_activity("Captura encerrada", "youtube")
                self.is_stopping = False
                return {"ok": True, "message": "Captura encerrada."}
            self._add_activity("A captura ainda está encerrando", "orange")
            return {
                "ok": False,
                "message": "A captura ainda está encerrando. Aguarde e tente novamente.",
            }

    def apply_overlay(self, payload):
        target = str((payload or {}).get("target", "chat")).lower()
        source = {
            "html": str((payload or {}).get("html", engine.LIVE_HTML)),
            "css": str((payload or {}).get("css", engine.LIVE_CSS)),
            "js": str((payload or {}).get("js", engine.LIVE_JS)),
        }
        validation = self.validate_overlay(source)
        if not validation["valid"]:
            return {"ok": False, "message": " ".join(validation["errors"]), "errors": validation["errors"]}
        with self.lock:
            try:
                if target == "events":
                    chat_source = {"html": engine.LIVE_HTML, "css": engine.LIVE_CSS, "js": engine.LIVE_JS}
                    self._save_overlay_settings({"chat": chat_source, "events": source})
                    self.event_overlay = source
                else:
                    self._save_overlay_settings(source)
            except OSError as error:
                self._log(f"[OVERLAY] Falha ao salvar personalização: {error}", "youtube", activity=False)
                return {"ok": False, "message": "Não foi possível salvar a personalização localmente."}
            if target != "events":
                engine.LIVE_HTML = source["html"]
                engine.LIVE_CSS = source["css"]
                engine.LIVE_JS = source["js"]
            try:
                self.save_overlay_named(target, "ativo", source)
                self.save_overlay_history(target, source)
            except OSError:
                pass
            self.overlay_is_saved = True
            self._add_activity("Overlay atualizado em tempo real", "green")
        return {"ok": True, "message": "Overlay salvo e aplicado no OBS."}

    def overlay_source(self):
        with self.lock:
            return {
                "html": engine.LIVE_HTML,
                "css": engine.LIVE_CSS,
                "js": engine.LIVE_JS,
                "saved": self.overlay_is_saved,
                "events": dict(self.event_overlay),
            }

    def _load_overlay_settings(self):
        if not os.path.isfile(self.overlay_config_path):
            return
        try:
            with open(self.overlay_config_path, "r", encoding="utf-8") as settings_file:
                source = json.load(settings_file)
            if not isinstance(source, dict):
                raise ValueError("formato inválido")
            if isinstance(source.get("chat"), dict):
                self.event_overlay = source.get("events") or self.event_overlay
                source = source["chat"]
            values = {}
            for name in ("html", "css", "js"):
                value = source.get(name)
                if not isinstance(value, str):
                    raise ValueError(f"campo {name} inválido")
                if len(value.encode("utf-8")) > MAX_OVERLAY_SECTION_BYTES:
                    raise ValueError(f"campo {name} excede 1 MB")
                values[name] = value
            engine.LIVE_HTML = values["html"]
            engine.LIVE_CSS = values["css"]
            engine.LIVE_JS = values["js"]
            self.overlay_is_saved = True
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self._log(f"[OVERLAY] Personalização ignorada: {error}", "youtube", activity=False)

    def _save_overlay_settings(self, source):
        directory = os.path.dirname(self.overlay_config_path)
        os.makedirs(directory, exist_ok=True)
        temporary_path = f"{self.overlay_config_path}.tmp"
        with open(temporary_path, "w", encoding="utf-8") as settings_file:
            json.dump(source, settings_file, ensure_ascii=False, indent=2)
            settings_file.flush()
            os.fsync(settings_file.fileno())
        os.replace(temporary_path, self.overlay_config_path)

    def _load_channels(self):
        if not os.path.isfile(self.channels_config_path):
            return
        try:
            with open(self.channels_config_path, "r", encoding="utf-8") as settings_file:
                saved = json.load(settings_file)
            if not isinstance(saved, dict):
                raise ValueError("formato inválido")
            for platform in PLATFORMS:
                value = saved.get(platform, "")
                if isinstance(value, str):
                    self.channels[platform] = normalize_channel_input(value)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self._log(f"[PLATAFORMAS] Canais salvos ignorados: {error}", "youtube", activity=False)

    def _persist_channels(self, channels):
        try:
            directory = os.path.dirname(self.channels_config_path)
            os.makedirs(directory, exist_ok=True)
            temporary_path = f"{self.channels_config_path}.tmp"
            with open(temporary_path, "w", encoding="utf-8") as settings_file:
                json.dump(channels, settings_file, ensure_ascii=False, indent=2)
                settings_file.flush()
                os.fsync(settings_file.fileno())
            os.replace(temporary_path, self.channels_config_path)
        except OSError as error:
            self._log(f"[PLATAFORMAS] Falha ao salvar canais: {error}", "youtube", activity=False)

    def snapshot(self):
        with self.lock:
            elapsed = 0 if self.session_started is None else int(time.monotonic() - self.session_started)
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            try:
                cpu = self.process.cpu_percent()
                memory = self.process.memory_info().rss / (1024 * 1024)
            except psutil.Error:
                cpu, memory = 0, 0
            return {
                "version": APP_VERSION,
                "capturing": self.is_capturing,
                "platformRegistry": self.platform_registry(),
                "eventUrl": engine.overlay_url("events"),
                "chatUrl": engine.overlay_url("chat"),
                "platforms": {
                    platform: {
                        "connected": self.connected[platform],
                        "status": self.status_labels[platform],
                        "count": self.counts[platform],
                        "channel": self.channels[platform],
                        "lastActivity": self.last_activity[platform],
                    }
                    for platform in PLATFORMS
                },
                "messages": list(self.messages),
                "events": list(self.events_feed),
                "donations": self.donation_ledger.snapshot()[-20:],
                "activity": list(self.activity)[:8],
                "logs": list(self.logs)[-100:],
                "stats": {
                    "messages": sum(self.counts.values()),
                    "platforms": sum(1 for value in self.connected.values() if value),
                    "session": f"{hours:02}:{minutes:02}:{seconds:02}",
                    "resources": f"{cpu:.0f}% / {memory:.0f} MB",
                },
            }

    def _receive_message(self, user, message, platform):
        if platform not in PLATFORMS:
            self.record_operational_log(f"[CHAT] Mensagem descartada: plataforma inválida {platform!r}", "orange")
            return
        with self.lock:
            self.last_activity[platform] = int(time.time() * 1000)
            record = normalize_chat_message({
                "user": user, "displayName": user, "message": message,
                "platform": platform, "timestamp": int(time.time() * 1000),
            })
            if record.get("userId") in self.ignored_users or record.get("user") in self.ignored_users:
                self.record_operational_log(f"[CHAT] Mensagem descartada por moderação: {sanitize_text(user, 160)}", "orange")
                return
            record["time"] = datetime.now().strftime("%H:%M:%S")
            with engine.CHAT_LOCK:
                engine.MESSAGE_SEQUENCE += 1
                record["id"] = engine.MESSAGE_SEQUENCE
                enriched = dict(record)
                engine.CHAT_MESSAGES.append(enriched)
                del engine.CHAT_MESSAGES[:-engine.MAX_MESSAGES]
            self.messages.append(record)
            self.counts[platform] += 1
            engine.publish_realtime("chat", enriched)
            self._log(f"[{platform.upper()}] {sanitize_text(user, 160)}: {sanitize_text(message)}", platform, activity=False)

    def _receive_status(self, platform, status):
        if platform not in PLATFORMS:
            self.record_operational_log(f"[STATUS] Atualização descartada: plataforma inválida {platform!r}", "orange")
            return
        status = sanitize_text(status, 500)
        lower = status.lower()
        with self.lock:
            self.last_activity[platform] = int(time.time() * 1000)
            if "desconectado" in lower or "erro" in lower or "recusou" in lower or "offline" in lower:
                self._set_platform(platform, False, str(status))
            elif "conectado" in lower or "sintonizada" in lower:
                self._set_platform(platform, True, "Conectado")
            else:
                self.status_labels[platform] = str(status)
            self._log(f"[{platform.upper()}] {status}", platform)

    def _receive_event(self, event, platform):
        """Store a normalized platform event without mixing it into chat."""
        if platform not in PLATFORMS and platform not in PAYMENT_SOURCES:
            self.record_operational_log(f"[EVENTOS] Evento descartado: plataforma inválida {platform!r}", "orange")
            return
        try:
            if isinstance(event, str):
                record = {"type": "event", "title": event, "message": event}
            else:
                record = dict(event or {})
            record = normalize_event(record, platform=platform)
        except (TypeError, ValueError, OverflowError) as error:
            self.record_operational_log(f"[EVENTOS] Falha de parsing em {platform}: {error}", "orange")
            return
        record["timestamp"] = int(time.time() * 1000)
        event_type = record["type"]
        record["title"] = record["data"].get("title") or event_type.replace("_", " ").title()
        record["message"] = record["data"].get("message") or record["data"].get("text") or record["title"]
        record["time"] = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            if platform in self.last_activity:
                self.last_activity[platform] = int(time.time() * 1000)
            source_id = record["data"].get("eventId")
            if source_id not in (None, ""):
                now = time.monotonic()
                expired = [key for key, seen_at in self._event_dedup.items() if now - seen_at > EVENT_DEDUPE_TTL_SECONDS]
                for key in expired:
                    del self._event_dedup[key]
                dedup_key = f"{platform}:{event_type}:{source_id}"
                if dedup_key in self._event_dedup:
                    self.record_operational_log(f"[EVENTOS] Evento duplicado descartado: {dedup_key}", "orange")
                    return
                self._event_dedup[dedup_key] = now
            published = self.event_bus.publish(record)
            record["id"] = published["id"]
            self.events_feed.append(record)
            with engine.CHAT_LOCK:
                engine.EVENT_SEQUENCE += 1
                payload = dict(record)
                payload["id"] = engine.EVENT_SEQUENCE
                engine.EVENT_MESSAGES.append(payload)
                del engine.EVENT_MESSAGES[:-engine.MAX_MESSAGES]
            engine.publish_realtime("events", payload)
            self._log(f"[{platform.upper()}] {record['title']}", platform, activity=False)

    def confirm_donation(self, provider, donation):
        result = self.donation_ledger.confirm(donation)
        if not result.get("ok"):
            self.record_operational_log(f"[PAGAMENTOS] Doação rejeitada ({provider}): {result.get('message')}", "orange")
            return result
        if result.get("duplicate"):
            self.record_operational_log(f"[PAGAMENTOS] Webhook duplicado ignorado ({provider})", "orange")
            return result
        record = result.get("donation") or {}
        self._receive_event({"type": "donation", "data": record.get("eventData") or {}}, provider)
        self._log(f"[{str(provider).upper()}] Doação confirmada", str(provider), activity=False)
        return result

    def _bot_finished(self, platform, bot):
        with self.lock:
            if bot in self.bots:
                self.bots.remove(bot)
            self._set_platform(platform, False, "Desconectado")
            if self.is_capturing and not any(current.isRunning() for current in self.bots):
                self.is_capturing = False
            if self.is_stopping and not any(current.isRunning() for current in self.bots):
                self.is_stopping = False

    def _set_platform(self, platform, connected, label):
        self.connected[platform] = connected
        self.status_labels[platform] = label

    def _log(self, text, color="white", activity=True):
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "text": sanitize_text(text, 1000),
            "color": sanitize_text(color, 32),
        }
        self.logs.append(entry)
        if activity:
            self.activity.appendleft(entry)

    def record_operational_log(self, text, color="white"):
        self._log(str(text), color, activity=False)

    def _add_activity(self, text, color):
        self._log(text, color, activity=True)

    @staticmethod
    def _realtime_status():
        gateway = engine.REALTIME_GATEWAY
        if gateway is None:
            return {"available": False, "running": False, "port": None}
        try:
            running = bool(gateway.is_running())
        except Exception:
            running = False
        return {
            "available": True,
            "running": running,
            "port": getattr(gateway, "port", None),
        }

    def diagnostics_snapshot(self):
        with self.lock:
            connected = sum(1 for value in self.connected.values() if value)
            platform_status = {
                platform: {
                    "connected": self.connected[platform],
                    "status": self.status_labels[platform],
                    "lastActivity": self.last_activity[platform],
                }
                for platform in PLATFORMS
            }
            try:
                queue_depth = self.events.qsize()
            except (NotImplementedError, AttributeError):
                queue_depth = 0
            capturing = self.is_capturing
        with self.diagnostic_lock:
            diagnostic = {
                **self.diagnostic,
                "checks": dict(self.diagnostic.get("checks") or {}),
                "lastSample": dict(self.diagnostic["lastSample"]) if self.diagnostic.get("lastSample") else None,
            }
        realtime = self._realtime_status()
        return {
            "ok": True,
            "server": {
                "http": True,
                "websocket": realtime,
            },
            "capture": {
                "active": capturing,
                "connectedPlatforms": connected,
                "platformCount": len(PLATFORMS),
            },
            "queue": {
                "depth": queue_depth,
                "capacity": self.events.maxsize,
            },
            "platforms": platform_status,
            "diagnostic": diagnostic,
            "limits": {
                "minSeconds": DIAGNOSTIC_MIN_SECONDS,
                "maxSeconds": DIAGNOSTIC_MAX_SECONDS,
            },
            "updatedAt": int(time.time() * 1000),
        }

    def start_diagnostic(self, duration_seconds=60):
        try:
            duration = int(duration_seconds)
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "message": "A duração do teste precisa ser um número inteiro."}
        duration = max(DIAGNOSTIC_MIN_SECONDS, min(DIAGNOSTIC_MAX_SECONDS, duration))
        started_at = datetime.now().isoformat(timespec="seconds")
        started_monotonic = time.monotonic()
        with self.diagnostic_lock:
            if self.diagnostic.get("status") == "running":
                return {"ok": False, "message": "Já existe um teste de resiliência em andamento."}
            try:
                queue_depth = self.events.qsize()
            except (NotImplementedError, AttributeError):
                queue_depth = 0
            self.diagnostic = {
                "status": "running",
                "requestedSeconds": duration,
                "elapsedSeconds": 0,
                "startedAt": started_at,
                "finishedAt": None,
                "message": f"Teste de resiliência em andamento por {duration}s.",
                "checks": {
                    "samples": 0,
                    "maxQueueDepth": queue_depth,
                    "queueErrors": 0,
                    "gatewayDownSamples": 0,
                },
                "lastSample": None,
            }
            self._diagnostic_thread = threading.Thread(
                target=self._run_diagnostic,
                args=(duration, started_monotonic),
                name="DashboardDiagnostic",
                daemon=True,
            )
            self._diagnostic_thread.start()
        self._add_activity(f"Teste de resiliência iniciado ({duration}s)", "cyan")
        return {"ok": True, "message": self.diagnostic["message"], "diagnostic": self.diagnostics_snapshot()["diagnostic"]}

    def _run_diagnostic(self, duration, started_monotonic):
        deadline = started_monotonic + duration
        while not self.closed:
            now = time.monotonic()
            try:
                queue_depth = self.events.qsize()
                queue_error = False
            except (NotImplementedError, AttributeError):
                queue_depth = 0
                queue_error = True
            realtime = self._realtime_status()
            with self.diagnostic_lock:
                checks = self.diagnostic["checks"]
                checks["samples"] += 1
                checks["maxQueueDepth"] = max(checks["maxQueueDepth"], queue_depth)
                if queue_error:
                    checks["queueErrors"] += 1
                if realtime["available"] and not realtime["running"]:
                    checks["gatewayDownSamples"] += 1
                self.diagnostic["elapsedSeconds"] = min(duration, int(now - started_monotonic))
                self.diagnostic["lastSample"] = {
                    "queueDepth": queue_depth,
                    "gateway": realtime,
                    "capturing": self.is_capturing,
                }
            if now >= deadline:
                break
            time.sleep(min(1.0, max(0.1, deadline - now)))
        with self.diagnostic_lock:
            if self.diagnostic.get("status") != "running":
                return
            cancelled = self.closed
            self.diagnostic["status"] = "cancelled" if cancelled else "completed"
            self.diagnostic["elapsedSeconds"] = min(duration, int(time.monotonic() - started_monotonic))
            self.diagnostic["finishedAt"] = datetime.now().isoformat(timespec="seconds")
            self.diagnostic["message"] = (
                "Teste interrompido durante o encerramento da aplicação."
                if cancelled else "Teste concluído sem interromper a captura."
            )
        if not cancelled:
            self._add_activity("Teste de resiliência concluído", "green")

    def shutdown(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            bots = list(self.bots)
            self.is_capturing = False
        for bot in bots:
            try:
                bot.running = False
                bot.requestInterruption()
                bot.wait(1200)
            except Exception:
                pass
        with self.lock:
            self.bots.clear()
