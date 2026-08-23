"""Channel abstraction: anything that moves inbound/outbound chat messages."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Inbound:
    phone: str
    text: str


@dataclass
class Outbound:
    phone: str
    text: str


class Channel(ABC):
    """A channel registers its routes on the FastAPI app and turns transports into
    calls to app.flows.handle_message(phone, text) -> list[str] replies."""

    name: str = "base"

    @abstractmethod
    def register(self, app) -> None:  # pragma: no cover - interface
        ...
