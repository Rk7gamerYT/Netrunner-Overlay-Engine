import sys
import os
import asyncio

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    ConnectEvent,
    DisconnectEvent
)

from core.base_bot import BaseBot


class TikTokBot(BaseBot):

    def run(self):

        self.running = True
        username = self.channel_name.lstrip('@')

        asyncio.run(self.start_bot(username))

    async def start_bot(self, username):

        while self.running:

            client = None

            try:

                client = TikTokLiveClient(
                    unique_id=username
                )

                @client.on(ConnectEvent)
                async def on_connect(event):

                    self.status_update.emit(
                        f"TikTok conectado: @{username}"
                    )

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

                @client.on(DisconnectEvent)
                async def on_disconnect(event):

                    self.status_update.emit(
                        "🔴 TikTok desconectado."
                    )

                self.status_update.emit(
                    f"Conectando ao TikTok: @{username}"
                )

                await client.start()

            except Exception as e:

                if not self.running:
                    break

                self.status_update.emit(
                    f"Erro TikTok: {str(e)}"
                )

                self.status_update.emit(
                    "Reconectando em 10 segundos..."
                )

                await asyncio.sleep(10)

            finally:

                try:
                    if client:
                        await client.disconnect()

                except:
                    pass