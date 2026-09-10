from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


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
    display = str(data.get("displayName") or data.get("user") or "Usuário")
    return ChatMessage(
        id=int(data.get("id") or 0), platform=str(data.get("platform") or ""),
        user=str(data.get("user") or display), displayName=display,
        userId=str(data["userId"]) if data.get("userId") is not None else None,
        message=str(data.get("message") or ""), color=data.get("color"),
        timestamp=int(data.get("timestamp") or 0), messageType=str(data.get("messageType") or "default"),
        badges=list(data.get("badges") or []), emotes=list(data.get("emotes") or []),
        metadata=dict(data.get("metadata") or {}),
    ).to_dict()
