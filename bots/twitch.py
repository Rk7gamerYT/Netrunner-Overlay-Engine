import random
import re
import socket
import ssl
import time
from urllib.parse import urlparse

from core.base_bot import BaseBot


TWITCH_HOST = "irc.chat.twitch.tv"
TWITCH_PORT = 6697


class TwitchBot(BaseBot):

    def __init__(self, channel_name):

        super().__init__(channel_name)

        self.message_cache = {}

        self.sock = None


    def _normalize_channel(self):

        value = self.channel_name.strip()

        if "://" in value:

            value = urlparse(value).path.strip("/").split("/")[0]

        channel = value.lstrip("#@").strip().lower()

        if not re.fullmatch(r"[a-z0-9_]{3,25}", channel):

            raise ValueError(
                "Informe o nome ou a URL válida de um canal Twitch."
            )

        return channel


    def _connect(self, channel):

        raw_socket = socket.create_connection(
            (TWITCH_HOST, TWITCH_PORT),
            timeout=10
        )

        context = ssl.create_default_context()

        self.sock = context.wrap_socket(
            raw_socket,
            server_hostname=TWITCH_HOST
        )

        self.sock.settimeout(1.0)

        nickname = f"justinfan{random.randint(10000, 99999)}"

        commands = (
            "CAP REQ :twitch.tv/tags twitch.tv/commands\r\n"
            f"NICK {nickname}\r\n"
            f"JOIN #{channel}\r\n"
        )

        self.sock.sendall(
            commands.encode("utf-8")
        )


    def _close_socket(self):

        if not self.sock:
            return

        try:
            self.sock.shutdown(socket.SHUT_RDWR)

        except Exception:
            pass

        try:
            self.sock.close()

        except Exception:
            pass

        self.sock = None


    def _parse_tags(self, line):

        if not line.startswith("@"):
            return {}

        raw_tags = line.split(" ", 1)[0][1:]

        tags = {}

        for item in raw_tags.split(";"):

            key, _, value = item.partition("=")

            tags[key] = value

        return tags


    def _handle_privmsg(self, line):

        match = re.search(
            r":(?P<user>[^! ]+)![^ ]+ PRIVMSG #[^ ]+ :(?P<message>.*)$",
            line
        )

        if not match:
            return

        tags = self._parse_tags(line)

        user = tags.get("display-name") or match.group("user")

        message = match.group("message").strip()

        message_id = tags.get("id")

        cache_id = message_id or f"{user}:{message}"

        now = time.monotonic()

        if cache_id in self.message_cache:
            return

        self.message_cache[cache_id] = now

        expired = [

            key

            for key, timestamp in self.message_cache.items()

            if now - timestamp > 60
        ]

        for key in expired:
            del self.message_cache[key]

        if message:

            self.new_message.emit(
                user,
                message,
                "twitch"
            )


    def _listen(self, channel):

        buffer = ""

        joined = False

        connected_at = time.monotonic()

        while self.running:

            try:

                data = self.sock.recv(8192)

            except socket.timeout:

                if not joined and time.monotonic() - connected_at > 12:
                    raise TimeoutError(
                        f"A Twitch não confirmou o canal #{channel}."
                    )

                continue

            if not data:
                raise ConnectionError("A Twitch encerrou a conexão.")

            buffer += data.decode(
                "utf-8",
                errors="replace"
            )

            lines = buffer.split("\r\n")

            buffer = lines.pop()

            for line in lines:

                if line.startswith("PING"):

                    payload = line.split(" ", 1)[1]

                    self.sock.sendall(
                        f"PONG {payload}\r\n".encode("utf-8")
                    )

                    continue

                if " RECONNECT" in line:
                    raise ConnectionError(
                        "A Twitch solicitou reconexão."
                    )

                if "Login authentication failed" in line:
                    raise ConnectionError(
                        "A Twitch recusou a conexão anônima."
                    )

                if (
                    f" JOIN #{channel}" in line
                    or f"ROOMSTATE #{channel}" in line
                ):

                    if not joined:

                        joined = True

                        self.status_update.emit(
                            f"Twitch conectado: #{channel}"
                        )

                if " PRIVMSG " in line:

                    self._handle_privmsg(line)


    def run(self):

        self.running = True

        try:

            channel = self._normalize_channel()

        except Exception as error:

            self.running = False

            self.status_update.emit(
                f"Erro Twitch: {error}"
            )

            return

        reconnect_delay = 2

        while self.running:

            try:

                self.status_update.emit(
                    f"Conectando à Twitch: #{channel}"
                )

                self._connect(channel)

                self._listen(channel)

                reconnect_delay = 2

            except Exception as error:

                if self.running:

                    self.status_update.emit(
                        f"Erro Twitch: {error}"
                    )

            finally:

                self._close_socket()

            if not self.running:
                break

            self.status_update.emit(
                f"Reconectando Twitch em {reconnect_delay}s..."
            )

            deadline = time.monotonic() + reconnect_delay

            while self.running and time.monotonic() < deadline:
                time.sleep(0.25)

            reconnect_delay = min(
                reconnect_delay * 2,
                15
            )

        self.running = False
