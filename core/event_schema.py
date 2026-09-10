from dataclasses import asdict, dataclass, field
from typing import Any, Dict


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
    data = dict(payload or {})
    data.update(overrides)
    return NetrunnerEvent(
        id=int(data.get("id") or 0), platform=str(data.get("platform") or ""),
        type=str(data.get("type") or "system"), timestamp=int(data.get("timestamp") or 0),
        data=dict(data.get("data") or {}),
    ).to_dict()
