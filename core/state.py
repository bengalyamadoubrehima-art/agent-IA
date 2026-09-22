from enum import Enum


class JarvisState(str, Enum):

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    ERROR = "error"


class StateManager:

    def __init__(self, event_bus=None):

        self._state = JarvisState.IDLE
        self._listeners = []
        self.event_bus = event_bus

    @property
    def state(self):
        return self._state

    def set_state(self, state):

        if not isinstance(
            state,
            JarvisState
        ):
            state = JarvisState(state)

        old_state = self._state

        if old_state == state:
            return

        self._state = state

        for listener in list(
            self._listeners
        ):

            try:
                listener(state)

            except Exception:
                pass

        if self.event_bus:

            self.event_bus.emit(
                "state.changed",
                {
                    "old": old_state.value,
                    "new": state.value,
                }
            )

    def add_listener(self, listener):

        if listener not in self._listeners:
            self._listeners.append(
                listener
            )

    def remove_listener(self, listener):

        if listener in self._listeners:
            self._listeners.remove(
                listener
            )

    def is_state(self, state):

        if not isinstance(
            state,
            JarvisState
        ):
            state = JarvisState(state)

        return self._state == state

    def reset(self):

        self.set_state(
            JarvisState.IDLE
        )