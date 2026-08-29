import json
import os
import queue
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


PLATFORMS = {
    "twitch": TwitchBot,
    "youtube": YouTubeBot,
    "tiktok": TikTokBot,
    "kick": KickBot,
}

OVERLAY_CONFIG_ENV = "NETRUNNER_OVERLAY_CONFIG"
MAX_OVERLAY_SECTION_BYTES = 1024 * 1024


def default_overlay_config_path():
    override = os.environ.get(OVERLAY_CONFIG_ENV)
    if override:
        return os.path.abspath(override)
    base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base_dir, "NetrunnerOverlay", "overlay.json")


class WebDashboardController:
    """Thread-safe bridge between the web dashboard and the capture workers."""

    def __init__(self, overlay_config_path=None):
        self.events = queue.Queue()
        self.lock = threading.RLock()
        self.bots = []
        self.messages = deque(maxlen=50)
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
        self.overlay_is_saved = False
        self._load_overlay_settings()
        self._add_activity("Aplicação v1.2.0 iniciada", "cyan")
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
            elif kind == "status":
                self._receive_status(*event[1:])
            elif kind == "finished":
                self._bot_finished(*event[1:])

    def start_capture(self, channels):
        with self.lock:
            if self.is_capturing or self.is_stopping:
                return {"ok": False, "message": "A captura já está ativa."}

            clean = {
                platform: str((channels or {}).get(platform, "")).strip()
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

    def stop_capture(self):
        with self.lock:
            if self.is_stopping:
                return {"ok": False, "message": "A captura já está encerrando."}
            self.is_stopping = True
            self.is_capturing = False
            bots = list(self.bots)
            for bot in bots:
                bot.running = False
                bot.requestInterruption()
            for platform in PLATFORMS:
                self._set_platform(platform, False, "Desconectado")
            self._add_activity("Captura encerrada", "youtube")
            self.is_stopping = False
            return {"ok": True, "message": "Captura encerrada."}

    def apply_overlay(self, payload):
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
                self._save_overlay_settings(source)
            except OSError as error:
                self._log(f"[OVERLAY] Falha ao salvar personalização: {error}", "youtube", activity=False)
                return {"ok": False, "message": "Não foi possível salvar a personalização localmente."}
            engine.LIVE_HTML = source["html"]
            engine.LIVE_CSS = source["css"]
            engine.LIVE_JS = source["js"]
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
            }

    def _load_overlay_settings(self):
        if not os.path.isfile(self.overlay_config_path):
            return
        try:
            with open(self.overlay_config_path, "r", encoding="utf-8") as settings_file:
                source = json.load(settings_file)
            if not isinstance(source, dict):
                raise ValueError("formato inválido")
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
            record = {
                "user": str(user),
                "message": str(message),
                "platform": platform,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
            self.messages.append(record)
            self.counts[platform] += 1
            with engine.CHAT_LOCK:
                engine.MESSAGE_SEQUENCE += 1
                engine.CHAT_MESSAGES.append({
                    "id": engine.MESSAGE_SEQUENCE,
                    "user": record["user"],
                    "message": record["message"],
                    "platform": platform,
                })
                del engine.CHAT_MESSAGES[:-engine.MAX_MESSAGES]
            self._log(f"[{platform.upper()}] {user}: {message}", platform, activity=False)

    def _receive_status(self, platform, status):
        if platform not in PLATFORMS:
            return
        lower = str(status).lower()
        with self.lock:
            if "conectado" in lower or "sintonizada" in lower:
                self._set_platform(platform, True, "Conectado")
            elif "desconectado" in lower or "erro" in lower:
                self._set_platform(platform, False, "Desconectado")
            else:
                self.status_labels[platform] = str(status)
            self._log(f"[{platform.upper()}] {status}", platform)

    def _bot_finished(self, platform, bot):
        with self.lock:
            if bot in self.bots:
                self.bots.remove(bot)
            self._set_platform(platform, False, "Desconectado")
            if self.is_capturing and not any(current.isRunning() for current in self.bots):
                self.is_capturing = False

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
