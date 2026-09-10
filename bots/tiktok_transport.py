"""Compatibility fixes for the pinned TikTokLive 7.0.0 transport."""
import asyncio
import inspect
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from TikTokLive import TikTokLiveClient as UpstreamTikTokLiveClient
from TikTokLive.client.ws.ws_connect import WebcastConnect


def build_webcast_uri(response, base_params, append_query=""):
    """Encode values without overwriting the server's signed route parameters."""
    server = urlsplit(response.push_server)
    if server.scheme != "wss" or not server.hostname or server.username:
        raise ValueError("Invalid secure TikTok WebSocket address")
    params = dict(parse_qsl(server.query, keep_blank_values=True))
    params.update(base_params)
    # TikTokLive ships browser_version percent-encoded; normalize that preset
    # before encoding the complete query. Never decode opaque signed tokens.
    if "browser_version" in params:
        params["browser_version"] = unquote(str(params["browser_version"]))
    params.update(response.route_params)
    query = urlencode(params, quote_via=quote)
    # The relay consumes structured route parameters and doesn't need the
    # duplicate version_code used by the direct TikTok endpoint.
    if server.hostname == "tiktok.com" or server.hostname.endswith(".tiktok.com"):
        if append_query:
            query += "&" + append_query.lstrip("?&")
    return urlunsplit((server.scheme, server.netloc, server.path, query, ""))


class CompatibleWebcastConnect(WebcastConnect):
    def __init__(self, initial_webcast_response, base_uri_params,
                 base_uri_append_str, uri=None, **kwargs):
        super().__init__(
            initial_webcast_response=initial_webcast_response,
            base_uri_params=base_uri_params,
            base_uri_append_str=base_uri_append_str,
            uri=uri or build_webcast_uri(
                initial_webcast_response, base_uri_params, base_uri_append_str
            ),
            **kwargs,
        )

    async def __aiter__(self):
        async for frame, response in super().__aiter__():
            if frame is None:
                # Upstream yields this only AFTER the WebSocket upgrade.
                # The relay currently omits is_first from its bootstrap. Mark
                # the bootstrap so TikTokLive joins the room, starts heartbeats
                # and emits ConnectEvent. A failed handshake never gets here.
                response.is_first = True
            yield frame, response


class TikTokLiveClient(UpstreamTikTokLiveClient):
    def __init__(self, *args, **kwargs):
        kwargs["ws_kwargs"] = {"open_timeout": 20, "close_timeout": 2, **kwargs.get("ws_kwargs", {})}
        super().__init__(*args, **kwargs)
        # Instance-local adapter for the pinned 7.0.0 private transport seam.
        self._ws._connect_generator_class = CompatibleWebcastConnect

    async def connect(self, callback=None, **kwargs):
        # Upstream connect handles cancellation with run_until_complete on an
        # already running loop. Keep lifecycle handling asynchronous instead.
        try:
            task = await self.start(**kwargs)
            if callback is not None:
                result = callback() if callable(callback) else callback
                if inspect.isawaitable(result):
                    asyncio.create_task(result)
            await asyncio.shield(task)
            return task
        finally:
            await self.disconnect()

    async def disconnect(self, close_client=False):
        try:
            await asyncio.wait_for(self._ws.disconnect(), timeout=3)
        finally:
            task, self._event_loop_task = self._event_loop_task, None
            ping = self._ws._ping_loop
            pending = [t for t in (task, ping) if t is not None and t is not asyncio.current_task()]
            for t in pending:
                if not t.done():
                    t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            self._ws._ping_loop = None
            self._room_id = None
            if close_client:
                await self.close()

    async def close(self):
        await self._web.close()
        await self._web.signer.sdk_client.get_async_httpx_client().aclose()
