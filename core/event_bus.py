import threading
import time


class EventBus:
    def __init__(self, max_events=200):
        self._events = []
        self._lock = threading.RLock()
        self._next_id = int(time.time() * 1000) * 1000
        self.max_events = max_events

    def publish(self, event):
        with self._lock:
            self._next_id += 1
            item = dict(event)
            item["id"] = self._next_id
            item.setdefault("timestamp", int(time.time() * 1000))
            self._events.append(item)
            del self._events[:-self.max_events]
            return dict(item)

    def snapshot(self, after=0):
        with self._lock:
            return [dict(item) for item in self._events if item.get("id", 0) > after]

