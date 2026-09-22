from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


@dataclass
class JarvisEvent:
    """
    Événement envoyé à travers le système JARVIS.
    """

    name: str
    data: dict[str, Any] = field(
        default_factory=dict
    )
    timestamp: datetime = field(
        default_factory=datetime.now
    )


class EventBus:
    """
    Système central de communication entre
    les différents modules de JARVIS.
    """

    def __init__(self):

        self._listeners = {}

    def subscribe(
        self,
        event_name: str,
        listener: Callable
    ):

        listeners = self._listeners.setdefault(
            event_name,
            []
        )

        if listener not in listeners:
            listeners.append(listener)

    def unsubscribe(
        self,
        event_name: str,
        listener: Callable
    ):

        listeners = self._listeners.get(
            event_name,
            []
        )

        if listener in listeners:
            listeners.remove(listener)

    def emit(
        self,
        event_name: str,
        data=None
    ):

        event = JarvisEvent(
            name=event_name,
            data=data or {}
        )

        listeners = list(
            self._listeners.get(
                event_name,
                []
            )
        )

        for listener in listeners:

            try:
                listener(event)

            except Exception as error:
                print(
                    f"⚠️ Erreur événement "
                    f"{event_name} : {error}"
                )

        return event

    def clear(self):

        self._listeners.clear()