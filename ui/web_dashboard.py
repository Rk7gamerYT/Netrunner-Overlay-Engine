import json
import os
import queue
import re
import threading
import time
from collections import deque
from datetime import datetime

import psutil

import engine
from bots.kick import KickBot
from bots.tiktok import TikTokBot
from bots.twitch import TwitchBot
from bots.youtube import YouTubeBot
from core.chat_schema import normalize_chat_message
from core.event_schema import normalize_event
from core.event_bus import EventBus
from core.platforms import PLATFORM_REGISTRY


PLATFORMS = {
    "twitch": TwitchBot,
    "youtube": YouTubeBot,
    "tiktok": TikTokBot,
    "kick": KickBot,
}

OVERLAY_CONFIG_ENV = "NETRUNNER_OVERLAY_CONFIG"
CHANNELS_CONFIG_ENV = "NETRUNNER_CHANNELS_CONFIG"
MAX_OVERLAY_SECTION_BYTES = 1024 * 1024


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
        self.events = queue.Queue()
        self.lock = threading.RLock()
        self.bots = []
        self.messages = deque(maxlen=50)
        self.events_feed = deque(maxlen=80)
        self.event_bus = EventBus(max_events=200)
        self.ignored_users = set()
        self.activity = deque(maxlen=80)
        self.logs = deque(maxlen=200)
        self.counts = {platform: 0 for platform in PLATFORMS}
        self.connected = {platform: False for platform in PLATFORMS}
        self.status_labels = {platform: "Desconectado" for platform in PLATFORMS}
        self.channels = {platform: "" for platform in PLATFORMS}
        self.is_capturing = False
        self.is_stopping = False
        self.closed = False
        self.session_started = None
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent()
        self.overlay_config_path = overlay_config_path or default_overlay_config_path()
        self.overlay_library_root = os.path.join(os.path.dirname(self.overlay_config_path), "overlays")
        self.channels_config_path = channels_config_path or default_channels_config_path()
        self.overlay_is_saved = False
        self.event_overlay = {
            "html": engine.DEFAULT_EVENT_HTML,
            "css": engine.DEFAULT_EVENT_CSS,
            "js": engine.DEFAULT_EVENT_JS,
        }
        self._load_overlay_settings()
        self._load_channels()
        self._add_activity("Aplicação v1.2.9 iniciada", "cyan")
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
            kind = event[0]
            if kind == "message":
                self._receive_message(*event[1:])
            elif kind == "event":
                self._receive_event(*event[1:])
            elif kind == "status":
                self._receive_status(*event[1:])
            elif kind == "finished":
                self._bot_finished(*event[1:])

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
                    lambda user, message, source, q=self.events:
                    q.put(("message", user, message, source))
                )
                if hasattr(bot, "new_event"):
                    bot.new_event.connect(
                        lambda event, source=platform, q=self.events:
                        q.put(("event", event, source))
                    )
                bot.status_update.connect(
                    lambda status, source=platform, q=self.events:
                    q.put(("status", source, status))
                )
                bot.finished.connect(
                    lambda current=bot, source=platform, q=self.events:
                    q.put(("finished", source, current))
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
        return {
            "chat": {"name": "Chat compacto", "html": "<div id=\"log\"></div>", "css": engine.DEFAULT_LIVE_CSS, "js": engine.DEFAULT_LIVE_JS},
            "events": {"name": "Alertas de eventos", "html": engine.DEFAULT_EVENT_HTML, "css": engine.DEFAULT_EVENT_CSS, "js": engine.DEFAULT_EVENT_JS},
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
            message_id = str(payload.get("messageId") or "")
            with self.lock:
                self.messages = deque((m for m in self.messages if str(m.get("id")) != message_id), maxlen=50)
            self._receive_event(normalize_event(type="message_delete", data={"messageId": message_id}), payload.get("platform", "twitch"))
            return {"ok": True, "message": "Mensagem removida."}
        if action in {"user_messages_delete", "delete_user"}:
            user_id = str(payload.get("userId") or payload.get("user") or "")
            with self.lock:
                self.messages = deque((m for m in self.messages if str(m.get("userId") or m.get("user")) != user_id), maxlen=50)
            self._receive_event(normalize_event(type="user_messages_delete", data={"userId": user_id}), payload.get("platform", "twitch"))
            return {"ok": True, "message": "Mensagens do usuário removidas."}
        return {"ok": False, "message": "Ação de moderação desconhecida."}

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
        oversized = [
            name for name, value in source.items()
            if len(value.encode("utf-8")) > MAX_OVERLAY_SECTION_BYTES
        ]
        if oversized:
            return {"ok": False, "message": "A personalização excede o limite de 1 MB por campo."}
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
                "capturing": self.is_capturing,
                "platformRegistry": self.platform_registry(),
                "eventUrl": "http://127.0.0.1:5000/events",
                "chatUrl": "http://127.0.0.1:5000/overlay",
                "platforms": {
                    platform: {
                        "connected": self.connected[platform],
                        "status": self.status_labels[platform],
                        "count": self.counts[platform],
                        "channel": self.channels[platform],
                    }
                    for platform in PLATFORMS
                },
                "messages": list(self.messages),
                "events": list(self.events_feed),
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
            return
        with self.lock:
            record = normalize_chat_message({
                "user": user, "displayName": user, "message": message,
                "platform": platform, "timestamp": int(time.time() * 1000),
            })
            if record.get("userId") in self.ignored_users or record.get("user") in self.ignored_users:
                return
            record["time"] = datetime.now().strftime("%H:%M:%S")
            self.messages.append(record)
            self.counts[platform] += 1
            with engine.CHAT_LOCK:
                engine.MESSAGE_SEQUENCE += 1
                enriched = dict(record)
                enriched["id"] = engine.MESSAGE_SEQUENCE
                engine.CHAT_MESSAGES.append(enriched)
                del engine.CHAT_MESSAGES[:-engine.MAX_MESSAGES]
            self._log(f"[{platform.upper()}] {user}: {message}", platform, activity=False)

    def _receive_status(self, platform, status):
        if platform not in PLATFORMS:
            return
        lower = str(status).lower()
        with self.lock:
            if "desconectado" in lower or "erro" in lower or "recusou" in lower or "offline" in lower:
                self._set_platform(platform, False, str(status))
            elif "conectado" in lower or "sintonizada" in lower:
                self._set_platform(platform, True, "Conectado")
            else:
                self.status_labels[platform] = str(status)
            self._log(f"[{platform.upper()}] {status}", platform)

    def _receive_event(self, event, platform):
        """Store a normalized platform event without mixing it into chat."""
        if platform not in PLATFORMS:
            return
        if isinstance(event, str):
            record = {"type": "event", "title": event, "message": event}
        else:
            record = dict(event or {})
        record = normalize_event(record, platform=platform)
        record["timestamp"] = int(time.time() * 1000)
        event_type = record["type"]
        record["title"] = record["data"].get("title") or event_type.replace("_", " ").title()
        record["message"] = record["data"].get("message") or record["data"].get("text") or record["title"]
        record["time"] = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            published = self.event_bus.publish(record)
            record["id"] = published["id"]
            self.events_feed.append(record)
            with engine.CHAT_LOCK:
                engine.EVENT_SEQUENCE += 1
                payload = dict(record)
                payload["id"] = engine.EVENT_SEQUENCE
                engine.EVENT_MESSAGES.append(payload)
                del engine.EVENT_MESSAGES[:-engine.MAX_MESSAGES]
            self._log(f"[{platform.upper()}] {record['title']}", platform, activity=False)

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
        entry = {"time": datetime.now().strftime("%H:%M:%S"), "text": text, "color": color}
        self.logs.append(entry)
        if activity:
            self.activity.appendleft(entry)

    def _add_activity(self, text, color):
        self._log(text, color, activity=True)

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
