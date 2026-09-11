from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from core.sanitization import sanitize_text, sanitize_value


@dataclass
class ChatMessage:
    id: int = 0
    platform: str = ""
    user: str = ""
    displayName: str = ""
    userId: Optional[str] = None
    message: str = ""
    color: Optional[str] = None
    timestamp: int = 0
    messageType: str = "default"
    badges: List[Dict[str, Any]] = field(default_factory=list)
    emotes: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def normalize_chat_message(payload=None, **overrides):
    data = dict(payload or {})
    data.update(overrides)
    display = sanitize_text(data.get("displayName") or data.get("user") or "Usuário", 160)
    badges = data.get("badges") if isinstance(data.get("badges"), (list, tuple)) else []
    emotes = data.get("emotes") if isinstance(data.get("emotes"), (list, tuple)) else []
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return ChatMessage(
        id=int(data.get("id") or 0), platform=sanitize_text(data.get("platform") or "", 32),
        user=sanitize_text(data.get("user") or display, 160), displayName=display,
        userId=sanitize_text(data["userId"], 200) if data.get("userId") is not None else None,
        message=sanitize_text(data.get("message") or ""), color=sanitize_text(data.get("color"), 32) if data.get("color") else None,
        timestamp=int(data.get("timestamp") or 0), messageType=sanitize_text(data.get("messageType") or "default", 64),
        badges=sanitize_value(list(badges)[:100]), emotes=sanitize_value(list(emotes)[:100]),
        metadata=sanitize_value(metadata),
    ).to_dict()
