import signal
import re
import time
from html import unescape
from urllib.parse import parse_qs, urlparse

import pytchat
import requests
import core.base_bot


YOUTUBE_VIDEO_ID_PATTERN = re.compile(r"[0-9A-Za-z_-]{11}")


class YouTubeBot(core.base_bot.BaseBot):
    supports_viewer_count = True
    supports_chat_send = False

    @staticmethod
    def _compact(value):
        return re.sub(r"\s+", "", str(value or "").strip())

    @classmethod
    def _video_id_from_input(cls, value):
        source = cls._compact(value)
        if YOUTUBE_VIDEO_ID_PATTERN.fullmatch(source):
            return source

        url_source = source
        if "://" not in url_source and re.match(r"(?:www\.)?(?:youtube\.com|youtu\.be)/", url_source, re.IGNORECASE):
            url_source = f"https://{url_source}"
        parsed = urlparse(url_source if "://" in url_source else "")
        if parsed.query:
            candidate = parse_qs(parsed.query).get("v", [""])[0]
            if YOUTUBE_VIDEO_ID_PATTERN.fullmatch(candidate):
                return candidate

        match = re.search(
            r"(?:youtu\.be/|/(?:watch|live)/)([0-9A-Za-z_-]{11})(?:[/?#]|$)",
            url_source,
            re.IGNORECASE,
        )
        return match.group(1) if match else None

    @classmethod
    def _resolve_channel_live(cls, source):
        value = cls._compact(source)
        if not value:
            raise ValueError("Informe um ID, URL ou @ do canal YouTube.")

        url_value = value
        if "://" not in url_value and re.match(r"(?:www\.)?(?:youtube\.com|youtu\.be)/", url_value, re.IGNORECASE):
            url_value = f"https://{url_value}"

        if "://" in url_value:
            parsed = urlparse(url_value)
            path = parsed.path.rstrip("/")
            if not path or path.endswith("/watch") or "/live/" in path:
                raise ValueError("A URL do YouTube não contém uma live válida.")
            live_url = f"{parsed.scheme}://{parsed.netloc}{path}"
            if not path.endswith("/live"):
                live_url += "/live"
        else:
            handle = value.lstrip("@").strip()
            if not re.fullmatch(r"[0-9A-Za-z._-]+", handle):
                raise ValueError("Use o @ ou o nome do canal YouTube sem espaços.")
            live_url = f"https://www.youtube.com/@{handle}/live"

        response = requests.get(
            live_url,
            headers={"User-Agent": "Mozilla/5.0 NetrunnerOverlay/1.2"},
            timeout=15,
        )
        response.raise_for_status()
        page = unescape(response.text)

        # /live normally redirects to the active broadcast. Prefer the final
        # URL and canonical/og:url metadata so an unrelated videoId embedded
        # in the page cannot win by accident.
        for candidate_source in (
            getattr(response, "url", ""),
        ):
            candidate = cls._video_id_from_input(candidate_source)
            if candidate:
                return candidate

        for tag in re.findall(r"<link\b[^>]*>", page, re.IGNORECASE):
            attrs = dict(re.findall(r"([:\w-]+)\s*=\s*[\"']([^\"']*)[\"']", tag))
            if attrs.get("rel", "").lower() == "canonical":
                candidate = cls._video_id_from_input(attrs.get("href", ""))
                if candidate:
                    return candidate

        for tag in re.findall(r"<meta\b[^>]*>", page, re.IGNORECASE):
            attrs = dict(re.findall(r"([:\w-]+)\s*=\s*[\"']([^\"']*)[\"']", tag))
            if attrs.get("property", "").lower() in {"og:url", "og:video"}:
                candidate = cls._video_id_from_input(attrs.get("content", ""))
                if candidate:
                    return candidate

        # The bootstrap payload is a fallback only when the page explicitly
        # identifies itself as live. This avoids selecting a recommended VOD.
        live_page = re.search(r'"(?:isLive|isLiveNow)"\s*:\s*true', page, re.IGNORECASE)
        if live_page:
            candidates = re.findall(r'"videoId"\s*:\s*"([0-9A-Za-z_-]{11})"', page)
            if candidates:
                return candidates[0]

        raise ValueError("Não encontrei uma live ativa para esse canal YouTube.")

    @classmethod
    def resolve_video_id(cls, value):
        source = cls._compact(value)
        video_id = cls._video_id_from_input(source)
        return video_id or cls._resolve_channel_live(source)

    @staticmethod
    def extract_viewer_count(source):
        """Extract the current concurrent viewer count from YouTube markup."""
        text = str(source or "")
        patterns = (
            r'"concurrentViewers"\s*:\s*"?(\d+)"?',
            r'"viewers"\s*:\s*"?(\d+)"?',
            r'"viewerCount"\s*:\s*"?(\d+)"?',
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _update_viewer_count(self, video_id):
        try:
            response = requests.get(
                f"https://www.youtube.com/watch?v={video_id}",
                headers={"User-Agent": "Mozilla/5.0 NetrunnerOverlay/1.3"},
                timeout=10,
            )
            response.raise_for_status()
            count = self.extract_viewer_count(response.text)
            if count is not None:
                self.viewer_count_update.emit(count)
        except Exception as error:
            self.status_update.emit(f"Aviso YouTube: espectadores indisponíveis ({error})")

    def _wait_before_retry(self, seconds):
        deadline = time.monotonic() + seconds
        while self.running and time.monotonic() < deadline:
            time.sleep(0.25)

    @staticmethod
    def _close_chat(chat):
        if chat is None:
            return
        for method_name in ("terminate", "close"):
            method = getattr(chat, method_name, None)
            if method is None:
                continue
            try:
                method()
            except Exception:
                pass

    def run(self):
        self.running = True
        reconnect_delay = 2

        while self.running:
            chat = None
            try:
                video_id = self.resolve_video_id(self.channel_name)

                original_signal = signal.signal
                def mock_signal(signum, handler): pass
                signal.signal = mock_signal
                try:
                    chat = pytchat.create(video_id=video_id)
                finally:
                    signal.signal = original_signal

                self.status_update.emit(f"Frequência YouTube sintonizada: {video_id}")
                self._update_viewer_count(video_id)
                next_viewer_sample = time.monotonic() + 30

                while self.running and chat.is_alive():
                    if time.monotonic() >= next_viewer_sample:
                        self._update_viewer_count(video_id)
                        next_viewer_sample = time.monotonic() + 30
                    for c in chat.get().sync_items():
                        self.new_message.emit(c.author.name, c.message, "youtube")
                        event_id = getattr(c, "id", None) or getattr(c, "messageId", None)
                        author_id = getattr(c.author, "channelId", None) or getattr(c.author, "id", None)
                        amount = getattr(c, "amountValue", None) or getattr(c, "amountString", None)
                        if amount:
                            self.new_event.emit({"type": "superchat", "data": {"eventId": event_id, "userId": author_id, "title": "Super Chat", "message": f"{c.author.name}: {amount}", "user": c.author.name, "displayName": c.author.name, "amount": amount}})
                        if getattr(c, "isMembership", False) or getattr(c, "memberMonth", None) or getattr(c, "isNewSponsor", False):
                            months = getattr(c, "memberMonth", None)
                            detail = c.author.name + (f" ({months} meses)" if months else "")
                            self.new_event.emit({"type": "member", "data": {"eventId": event_id, "userId": author_id, "title": "Novo membro", "message": detail, "user": c.author.name, "displayName": c.author.name, "months": months}})
                    time.sleep(1)

                if self.running:
                    raise ConnectionError("O YouTube encerrou a conexão do chat.")
                reconnect_delay = 2

            except ValueError as error:
                self.status_update.emit(f"Erro YT: {error}")
                break
            except Exception as error:
                if not self.running:
                    break
                self.status_update.emit(f"Erro YT: {error}")
                self.status_update.emit(f"Reconectando YouTube em {reconnect_delay}s...")
            finally:
                self._close_chat(chat)

            if not self.running:
                break
            self._wait_before_retry(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)

        self.running = False
