from dataclasses import asdict, dataclass, field
import time
from typing import Any, Dict

from core.sanitization import sanitize_text, sanitize_value


EVENT_TYPES = (
    "follow",
    "subscription",
    "gift",
    "like",
    "share",
    "raid",
    "bits",
    "point_redemption",
    "superchat",
    "member",
    "donation",
    "system",
)

EVENT_TYPE_ALIASES = {
    "sub": "subscription",
    "resub": "subscription",
    "subscribe": "subscription",
    "subscriber": "subscription",
    "membership": "member",
    "new_member": "member",
    "new_sponsor": "member",
    "super_chat": "superchat",
    "super chat": "superchat",
    "cheer": "bits",
    "bits_cheer": "bits",
    "follower": "follow",
    "new_follower": "follow",
    "followers": "follow",
    "gifts": "gift",
    "present": "gift",
    "presents": "gift",
    "likes": "like",
    "shares": "share",
    "hosts": "raid",
    "donate": "donation",
    "tip": "donation",
}


def normalize_event_type(value):
    event_type = sanitize_text(value or "system", 64).strip().lower().replace("-", "_").replace(" ", "_")
    return EVENT_TYPE_ALIASES.get(event_type, event_type if event_type in EVENT_TYPES else event_type)


@dataclass
class NetrunnerEvent:
    id: int = 0
    platform: str = ""
    type: str = "system"
    timestamp: int = 0
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def normalize_event(payload=None, **overrides):
    data = dict(payload) if isinstance(payload, dict) else {}
    data.update(overrides)
    event_data = sanitize_value(data.get("data") or {})
    if not isinstance(event_data, dict):
        event_data = {}

    # Adapters may provide the common fields either at the top level or
    # inside ``data``. Keep one stable shape for every overlay template.
    aliases = {
        "displayName": ("displayName", "display_name", "userName", "username"),
        "user": ("user", "username", "userName", "displayName"),
        "userId": ("userId", "user_id"),
        "message": ("message", "text", "content"),
        "title": ("title",),
        "amount": ("amount", "amountValue", "amountString"),
        "count": ("count", "quantity", "repeat_count"),
        "duration": ("duration", "durationMs", "duration_ms"),
        "eventId": ("eventId", "event_id", "sourceId", "source_id", "messageId", "message_id", "msg_id"),
    }
    for canonical, keys in aliases.items():
        if canonical in event_data and event_data[canonical] not in (None, ""):
            continue
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                event_data[canonical] = value
                break

    if event_data.get("displayName") in (None, "") and event_data.get("user"):
        event_data["displayName"] = event_data["user"]
    if event_data.get("user") in (None, "") and event_data.get("displayName"):
        event_data["user"] = event_data["displayName"]

    timestamp = int(data.get("timestamp") or time.time() * 1000)
    return NetrunnerEvent(
        id=int(data.get("id") or 0), platform=sanitize_text(data.get("platform") or "", 32),
        type=normalize_event_type(data.get("type")),
        timestamp=timestamp, data=sanitize_value(event_data),
    ).to_dict()
