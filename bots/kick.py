import html
import json
import re
import time
from urllib.parse import urlparse

import pysher
import requests

from core.base_bot import BaseBot


KICK_PUSHER_KEY = "32cbd69e4b950bf97679"
KICK_PUSHER_CLUSTER = "us2"
KICK_CHANNEL_API = "https://kick.com/api/v2/channels/{slug}"


class KickBot(BaseBot):

    supports_viewer_count = True
    supports_chat_send = False

    def __init__(self, channel_name):

        super().__init__(channel_name)

        self.pusher = None

        self.chatroom_id = None
        self._channel_slug = None

    @staticmethod
    def extract_viewer_count(payload):
        if not isinstance(payload, dict):
            return None
        livestream = payload.get("livestream") if isinstance(payload.get("livestream"), dict) else {}
        for value in (
            payload.get("viewer_count"), payload.get("viewerCount"),
            livestream.get("viewer_count"), livestream.get("viewerCount"),
        ):
            if value is not None and str(value).isdigit():
                return int(value)
        return None


    def _normalize_channel(self):

        value = self.channel_name.strip()

        if value.isdigit():
            return None, value

        if "://" in value:

            path = urlparse(value).path

            value = path.strip("/").split("/")[0]

        slug = value.lstrip("@").strip().lower()

        if not slug:
            raise ValueError("Informe o nome ou a URL do canal da Kick.")

        return slug, None


    def _resolve_chatroom_id(self):

        slug, numeric_id = self._normalize_channel()

        if numeric_id:
            return numeric_id, numeric_id

        self.status_update.emit(
            f"Resolvendo canal Kick: {slug}"
        )

        response = requests.get(
            KICK_CHANNEL_API.format(slug=slug),
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 NetrunnerOverlay/1.0"
            },
            timeout=10
        )

        if response.status_code == 404:
            raise ValueError(f"Canal Kick não encontrado: {slug}")

        response.raise_for_status()

        channel_data = response.json()
        self._channel_slug = slug
        self.viewer_count_update.emit(self.extract_viewer_count(channel_data) or 0)

        chatroom = channel_data.get("chatroom") or {}

        chatroom_id = chatroom.get("id")

        if not chatroom_id:
            raise ValueError(
                f"A Kick não retornou a sala de chat de {slug}."
            )

        return slug, str(chatroom_id)

    def _update_viewer_count(self):
        if not self._channel_slug:
            return
        try:
            response = requests.get(
                KICK_CHANNEL_API.format(slug=self._channel_slug),
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0 NetrunnerOverlay/1.3"},
                timeout=8,
            )
            response.raise_for_status()
            count = self.extract_viewer_count(response.json())
            if count is not None:
                self.viewer_count_update.emit(count)
        except Exception as error:
            self.status_update.emit(f"Aviso Kick: espectadores indisponíveis ({error})")


    def run(self):
        self.running = True
        reconnect_delay = 2
        while self.running:
            try:
                self._run_connection()
                reconnect_delay = 2
            except ValueError as error:
                self.status_update.emit(f"Erro Kick: {error}")
                break
            except Exception as error:
                if not self.running:
                    break
                self.status_update.emit(f"Erro Kick: {error}")
            if not self.running:
                break
            self.status_update.emit(f"Reconectando Kick em {reconnect_delay}s...")
            deadline = time.monotonic() + reconnect_delay
            while self.running and time.monotonic() < deadline:
                time.sleep(0.25)
            reconnect_delay = min(reconnect_delay * 2, 30)
        self.running = False

    def _run_connection(self):

        try:

            channel_label, self.chatroom_id = (
                self._resolve_chatroom_id()
            )

            self.pusher = pysher.Pusher(
                key=KICK_PUSHER_KEY,
                cluster=KICK_PUSHER_CLUSTER
            )

            def on_connect(_):

                if not self.running:
                    return

                channel_name = (
                    f"chatrooms.{self.chatroom_id}.v2"
                )

                channel = self.pusher.subscribe(
                    channel_name
                )

                channel.bind(
                    "App\\Events\\ChatMessageEvent",
                    self.handle_message
                )

                for event_name in (
                    "App\\Events\\SubscriptionEvent",
                    "App\\Events\\ChannelSubscriptionEvent",
                    "App\\Events\\GiftedSubscriptions",
                    "App\\Events\\FollowersUpdated",
                    "App\\Events\\FollowerEvent",
                    "App\\Events\\ChannelFollowEvent",
                    "App\\Events\\HostEvent",
                    "App\\Events\\RaidEvent",
                    "App\\Events\\HostRaidEvent",
                    "App\\Events\\TipEvent",
                    "App\\Events\\DonationEvent",
                    "App\\Events\\KicksGiftedEvent",
                    "App\\Events\\ChannelRewardRedeemedEvent",
                ):
                    channel.bind(event_name, lambda data, name=event_name: self.handle_event(data, name))

                self.status_update.emit(
                    "Kick conectado: "
                    f"{channel_label} (sala {self.chatroom_id})"
                )

            self.pusher.connection.bind(
                "pusher:connection_established",
                on_connect
            )

            self.pusher.connect()

            next_viewer_sample = time.monotonic() + 30
            while self.running:
                if time.monotonic() >= next_viewer_sample:
                    self._update_viewer_count()
                    next_viewer_sample = time.monotonic() + 30
                time.sleep(0.25)

        except Exception:
            raise

        finally:
            if self.pusher:

                try:
                    self.pusher.disconnect()

                except Exception:
                    pass

                self.pusher = None
                self._channel_slug = None


    def handle_message(self, data):

        if not self.running:
            return

        try:

            payload = json.loads(data)

            sender = payload.get("sender") or {}

            user = sender.get("username") or "Usuário"

            content = str(payload.get("content") or "")

            text = re.sub(
                r"<[^>]*>",
                "",
                content
            )

            text = html.unescape(text).strip()

            if not text:
                return

            self.new_message.emit(
                user,
                text,
                "kick"
            )

        except Exception as error:

            self.status_update.emit(
                f"Erro lendo mensagem Kick: {error}"
            )

    def handle_event(self, data, event_name=None):
        """Convert Kick activity payloads into the common event signal."""
        if not self.running:
            return
        try:
            payload = json.loads(data) if isinstance(data, str) else dict(data or {})
            event_name = str(event_name or payload.get("event") or payload.get("type") or payload.get("name") or "event")
            lowered = event_name.lower()
            sender = payload.get("sender") or payload.get("user") or payload.get("follower") or {}
            user = sender if isinstance(sender, str) else (sender.get("username") or sender.get("name") or "Usuário")
            user_id = None if isinstance(sender, str) else (sender.get("id") or sender.get("user_id"))
            if "follow" in lowered:
                event_type, title = "follow", "Novo seguidor"
            elif "subscription" in lowered or "subscriber" in lowered:
                event_type, title = "subscription", "Nova inscrição"
            elif "gift" in lowered:
                event_type, title = "gift", "Inscrições presenteadas"
            elif "raid" in lowered or "host" in lowered:
                event_type, title = "raid", "Raid recebida"
            elif "tip" in lowered or "donat" in lowered:
                event_type, title = "donation", "Doação recebida"
            elif "reward" in lowered:
                event_type, title = "point_redemption", "Resgate de pontos"
            elif "kick" in lowered:
                event_type, title = "bits", "Kicks recebidos"
            else:
                event_type, title = "system", "Evento Kick"
            event_id = payload.get("eventId") or payload.get("event_id") or payload.get("id") or payload.get("message_id")
            quantity = payload.get("quantity") or payload.get("amount") or payload.get("count")
            message = str(payload.get("message") or payload.get("content") or "")
            if not message:
                message = f"{user}" + (f" × {quantity}" if quantity else "")
            self.new_event.emit({
                "type": event_type,
                "data": {"eventId": event_id, "userId": user_id, "title": title, "message": message, "user": user, "displayName": user, "count": quantity, "amount": payload.get("amount"), "payload": payload},
            })
        except Exception as error:
            self.status_update.emit(f"Erro lendo evento Kick: {error}")
