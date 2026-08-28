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

    def __init__(self, channel_name):

        super().__init__(channel_name)

        self.pusher = None

        self.chatroom_id = None


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

        chatroom = channel_data.get("chatroom") or {}

        chatroom_id = chatroom.get("id")

        if not chatroom_id:
            raise ValueError(
                f"A Kick não retornou a sala de chat de {slug}."
            )

        return slug, str(chatroom_id)


    def run(self):

        self.running = True

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

                self.status_update.emit(
                    "Kick conectado: "
                    f"{channel_label} (sala {self.chatroom_id})"
                )

            self.pusher.connection.bind(
                "pusher:connection_established",
                on_connect
            )

            self.pusher.connect()

            while self.running:

                time.sleep(0.25)

        except Exception as error:

            self.status_update.emit(
                f"Erro Kick: {error}"
            )

        finally:

            self.running = False

            if self.pusher:

                try:
                    self.pusher.disconnect()

                except Exception:
                    pass

                self.pusher = None


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
