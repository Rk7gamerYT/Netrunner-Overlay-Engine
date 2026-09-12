import sys
import os
import asyncio
import threading
from urllib.parse import urlsplit

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from bots.tiktok_transport import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    DisconnectEvent,
    RoomUserSeqEvent,
)
try:
    from TikTokLive.events import GiftEvent, FollowEvent, LikeEvent, ShareEvent
except ImportError:  # versões antigas do TikTokLive
    GiftEvent = FollowEvent = LikeEvent = ShareEvent = None
from TikTokLive.client.errors import UserOfflineError
from websockets.exceptions import InvalidHandshake

from core.base_bot import BaseBot


def normalize_tiktok_channel(value):
    """Return the TikTok unique id from a handle, name, or profile URL."""
    raw = str(value or "").strip()
    if not raw:
        return ""

    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlsplit(candidate)
    if parsed.netloc and (parsed.path or "://" in raw):
        segment = next((part for part in parsed.path.split("/") if part), "")
        if segment:
            raw = segment

    return raw.lstrip("@").split("/", 1)[0].strip()


def websocket_rejection_status(error):
    """Return the HTTP status from old and new websockets exceptions."""
    status = getattr(error, "status_code", None)
    if status is not None:
        return status
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


class TikTokBot(BaseBot):

    supports_viewer_count = True
    supports_chat_send = False

    def __init__(self, channel_name):
        super().__init__(channel_name)
        self._client = None
        self._loop = None
        self._connect_task = None
        self._client_lock = threading.RLock()

    def requestInterruption(self):
        self.running = False
        with self._client_lock:
            loop = self._loop
        if loop is not None and loop.is_running():
            def cancel_connection():
                task = self._connect_task
                if task is not None and not task.done():
                    task.cancel()
            try:
                loop.call_soon_threadsafe(cancel_connection)
            except RuntimeError:
                pass

    async def _wait_before_retry(self, seconds):
        # Keep stop/reconnect responsive even while waiting after a failure.
        deadline = asyncio.get_running_loop().time() + seconds
        while self.running and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.1)

    def run(self):

        self.running = True
        username = normalize_tiktok_channel(self.channel_name)

        asyncio.run(self.start_bot(username))

    async def start_bot(self, username):
        self._loop = asyncio.get_running_loop()
        reconnect_delay = 2

        while self.running:

            client = None

            try:

                client = TikTokLiveClient(unique_id=username)
                with self._client_lock:
                    self._client = client

                @client.on(ConnectEvent)
                async def on_connect(event):

                    self.status_update.emit(
                        f"TikTok conectado: @{username}"
                    )

                @client.on(RoomUserSeqEvent)
                async def on_viewer_update(event):
                    count = getattr(event, "total_user", None) or getattr(event, "total", None) or getattr(event, "popularity", None)
                    try:
                        if count is not None:
                            self.viewer_count_update.emit(max(0, int(count)))
                    except (TypeError, ValueError):
                        pass

                @client.on(CommentEvent)
                async def on_comment(event):

                    if not self.running:
                        return

                    try:
                        nickname = getattr(
                            event.user,
                            "nickname",
                            "Usuário"
                        )

                    except:
                        nickname = "Usuário"

                    self.new_message.emit(
                        nickname,
                        event.comment,
                        "tiktok"
                    )

                def emit_live_event(event_type, event, title, message, extra=None):
                    if not self.running:
                        return
                    user = getattr(getattr(event, "user", None), "nickname", None) or "Usuário"
                    event_id = getattr(event, "msg_id", None) or getattr(event, "message_id", None)
                    data = {"eventId": event_id, "title": title, "message": f"{user}: {message}", "user": user, "displayName": user}
                    data.update(extra or {})
                    self.new_event.emit({"type": event_type, "data": data})

                if GiftEvent:
                    @client.on(GiftEvent)
                    async def on_gift(event):
                        gift = getattr(getattr(event, "gift", None), "name", None) or "Presente"
                        count = getattr(event, "repeat_count", 1) or 1
                        emit_live_event("gift", event, "Presente recebido", f"{gift} × {count}", {"giftName": gift, "count": count})
                if FollowEvent:
                    @client.on(FollowEvent)
                    async def on_follow(event):
                        emit_live_event("follow", event, "Novo seguidor", "começou a seguir")
                if LikeEvent:
                    @client.on(LikeEvent)
                    async def on_like(event):
                        count = getattr(event, "count", 1) or 1
                        emit_live_event("like", event, "Curtidas", f"+{count}", {"count": count})
                if ShareEvent:
                    @client.on(ShareEvent)
                    async def on_share(event):
                        emit_live_event("share", event, "Live compartilhada", "compartilhou a live")

                @client.on(DisconnectEvent)
                async def on_disconnect(event):

                    self.status_update.emit(
                        "🔴 TikTok desconectado."
                    )

                self.status_update.emit(
                    f"Conectando ao TikTok: @{username}"
                )

                # ``connect`` is the blocking API.  ``start`` only creates and
                # returns the websocket Task, so awaiting ``start`` alone
                # immediately enters the reconnect loop on TikTokLive 7.
                self._connect_task = asyncio.create_task(client.connect())
                await self._connect_task

                if self.running:
                    self.status_update.emit(
                        f"TikTok desconectado. Reconectando em {reconnect_delay}s..."
                    )
                    await self._wait_before_retry(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 30)

            except asyncio.CancelledError:
                if self.running:
                    raise
                break

            except UserOfflineError:

                if not self.running:
                    break

                self.status_update.emit(
                    "Live do TikTok offline. Inicie a live e clique em Reconectar."
                )
                break

            except InvalidHandshake as e:

                if not self.running:
                    break

                status = websocket_rejection_status(e)
                if status == 400:
                    self.status_update.emit(
                        "TikTok recusou o WebSocket (HTTP 400). "
                        "A solicitação de conexão foi rejeitada. Tente reconectar."
                    )
                    break

                self.status_update.emit(f"Erro TikTok: {str(e)}")
                self.status_update.emit("Reconectando em 10 segundos...")
                await self._wait_before_retry(10)
                reconnect_delay = 2

            except Exception as e:

                if not self.running:
                    break

                self.status_update.emit(
                    f"Erro TikTok: {str(e)}"
                )

                self.status_update.emit(
                    "Reconectando em 10 segundos..."
                )

                await self._wait_before_retry(10)
                reconnect_delay = 2

            finally:

                try:
                    if client:
                        await asyncio.wait_for(client.disconnect(), timeout=5)
                        close = getattr(client, "close", None)
                        if close is not None:
                            await close()

                except:
                    pass
                finally:
                    with self._client_lock:
                        if self._client is client:
                            self._client = None
                        self._connect_task = None
        self._loop = None
