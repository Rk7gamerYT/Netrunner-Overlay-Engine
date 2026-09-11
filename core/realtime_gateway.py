"""Small local WebSocket gateway used by Browser Source overlays."""

import asyncio
import json
import threading
from collections import deque
from urllib.parse import parse_qs, urlsplit

try:
    from websockets.asyncio.server import serve
except ImportError:  # websockets versions before the asyncio namespace
    try:
        from websockets.server import serve
    except ImportError:  # HTTP polling remains available without the optional transport
        serve = None


class LocalRealtimeGateway:
    def __init__(self, host="127.0.0.1", port=5001, history_size=200, history_provider=None, authenticator=None, logger=None):
        self.host = host
        self.port = port
        self.history_size = max(1, int(history_size))
        self.history_provider = history_provider
        self.authenticator = authenticator
        self.logger = logger
        self._thread = None
        self._loop = None
        self._server = None
        self._stop_event = None
        self._ready = threading.Event()
        self._error = None
        self._clients = {"chat": set(), "events": set()}
        self._history = {
            "chat": deque(maxlen=self.history_size),
            "events": deque(maxlen=self.history_size),
        }

    @staticmethod
    def _after_id(path):
        query = parse_qs(urlsplit(path).query)
        try:
            return max(0, int(query.get("after", [0])[0]))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _payload_id(payload):
        try:
            return int(payload.get("id", 0))
        except (AttributeError, TypeError, ValueError):
            return 0

    def _replay_after(self, topic, after_id):
        payloads = {}
        for payload in self._history[topic]:
            payload_id = self._payload_id(payload)
            if payload_id > after_id:
                payloads[payload_id] = dict(payload)
        if self.history_provider is not None:
            try:
                provided = self.history_provider(topic, after_id) or ()
            except Exception:
                provided = ()
            for payload in provided:
                payload_id = self._payload_id(payload)
                if payload_id > after_id:
                    payloads[payload_id] = dict(payload)
        return [payloads[payload_id] for payload_id in sorted(payloads)]

    async def _handler(self, websocket):
        request = getattr(websocket, "request", None)
        path = getattr(request, "path", "") or getattr(websocket, "path", "")
        path = str(path)
        topic = "events" if urlsplit(path).path.rstrip("/").endswith("/events") else "chat"
        if self.authenticator is not None:
            try:
                authorized = bool(self.authenticator(topic, path))
            except Exception as error:
                authorized = False
                self._log(f"[REALTIME] Falha ao validar WebSocket: {error}")
            if not authorized:
                self._log(f"[REALTIME] WebSocket {topic} recusado: token inválido ou revogado")
                await websocket.close(code=4401, reason="Unauthorized")
                return
        after_id = self._after_id(path)
        self._clients[topic].add(websocket)
        self._log(f"[REALTIME] WebSocket {topic} conectado")
        try:
            await websocket.send(json.dumps({"type": "hello", "topic": topic}))
            for payload in self._replay_after(topic, after_id):
                await websocket.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            await websocket.wait_closed()
        finally:
            self._clients[topic].discard(websocket)
            self._log(f"[REALTIME] WebSocket {topic} desconectado")

    def _log(self, text):
        if self.logger is None:
            return
        try:
            self.logger(text)
        except Exception:
            pass

    async def _broadcast(self, topic, payload):
        message = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        clients = tuple(self._clients.get(topic, ()))
        if not clients:
            return
        results = await asyncio.gather(
            *(client.send(message) for client in clients),
            return_exceptions=True,
        )
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                self._clients.get(topic, set()).discard(client)
                self._log(f"[REALTIME] Cliente {topic} removido após falha de envio: {result}")

    async def _publish(self, topic, payload):
        self._history[topic].append(dict(payload))
        await self._broadcast(topic, payload)

    async def _serve(self):
        self._stop_event = asyncio.Event()
        self._server = await serve(self._handler, self.host, self.port)
        if self._server.sockets:
            self.port = self._server.sockets[0].getsockname()[1]
        self._ready.set()
        await self._stop_event.wait()
        self._server.close()
        await self._server.wait_closed()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            if serve is None:
                raise RuntimeError("websockets is not installed")
            self._loop.run_until_complete(self._serve())
        except Exception as error:
            self._error = error
            self._ready.set()
        finally:
            self._loop.close()
            self._loop = None

    def start(self, timeout=5):
        if self.is_running():
            return True
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, name="NetrunnerRealtimeGateway", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self._ready.is_set() and self._error is None

    def publish(self, topic, payload):
        if topic not in self._clients or self._loop is None or self._stop_event is None:
            return False
        asyncio.run_coroutine_threadsafe(self._publish(topic, payload), self._loop)
        return True

    def stop(self, timeout=2):
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None

    def is_running(self):
        return bool(self._thread and self._thread.is_alive() and self._loop is not None)
