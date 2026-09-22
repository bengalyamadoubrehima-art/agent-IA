from dataclasses import dataclass
from typing import Any


@dataclass
class BridgeRequest:
    action: str
    payload: dict[str, Any]


@dataclass
class BridgeResponse:
    success: bool
    action: str
    result: Any = None
    error: str | None = None
