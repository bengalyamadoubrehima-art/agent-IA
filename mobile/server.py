import asyncio
import json
import os
import platform
import socket
import threading
from datetime import datetime

from dotenv import load_dotenv
from websockets.asyncio.server import serve


load_dotenv()

HOST = "0.0.0.0"
PORT = 8765

TOKEN = os.getenv("ANDROID_BRIDGE_TOKEN", "")


class MobileBridge:

    def __init__(
        self,
        orchestrator=None,
        state_manager=None,
        event_bus=None,
    ):
        self.orchestrator = orchestrator
        self.state_manager = state_manager
        self.event_bus = event_bus

        self.clients = set()

        self.loop = None
        self.server = None
        self.thread = None
        self.running = False

        self._register_events()

    # =========================================================
    # ÉVÉNEMENTS JARVIS
    # =========================================================

    def _register_events(self):

        if not self.event_bus:
            return

        events = [
            "state.changed",
            "tool.started",
            "tool.finished",
            "tool.failed",
            "tool.blocked",
            "tool.denied",
            "tool.confirmation_required",
            "voice.started",
            "voice.transcribed",
            "voice.speaking_started",
            "voice.speaking_finished",
            "voice.error",
        ]

        for event_name in events:
            self.event_bus.subscribe(
                event_name,
                lambda event, name=event_name:
                    self._event_received(name, event.data)
            )

    def _event_received(self, event_name, data):

        if not self.loop or not self.running:
            return

        message = {
            "type": "event",
            "event": event_name,
            "data": data or {},
        }

        asyncio.run_coroutine_threadsafe(
            self.broadcast(message),
            self.loop
        )

    # =========================================================
    # RÉPONSE
    # =========================================================

    @staticmethod
    def make_response(
        success,
        action,
        result=None,
        error=None,
    ):
        response = {
            "success": success,
            "action": action,
        }

        if result is not None:
            response["result"] = result

        if error is not None:
            response["error"] = error

        return response

    # =========================================================
    # ACTIONS
    # =========================================================

    async def execute_action(self, action, payload):

        if action == "ping":
            return self.make_response(
                True,
                action,
                "pong",
            )

        if action == "status":

            state = None

            if self.state_manager:
                state = self.state_manager.state.value

            return self.make_response(
                True,
                action,
                {
                    "jarvis": "online",
                    "bridge": "online",
                    "state": state,
                    "platform": platform.system(),
                    "hostname": socket.gethostname(),
                },
            )

        if action == "time":

            now = datetime.now().astimezone()

            return self.make_response(
                True,
                action,
                {
                    "datetime": now.isoformat(),
                    "timezone": now.tzname(),
                },
            )

        if action == "pc_info":

            return self.make_response(
                True,
                action,
                {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "python": platform.python_version(),
                    "hostname": socket.gethostname(),
                },
            )

        # -----------------------------------------------------
        # CHAT AVEC JARVIS
        # -----------------------------------------------------

        if action == "chat":

            if self.orchestrator is None:
                return self.make_response(
                    False,
                    action,
                    error="Orchestrateur JARVIS indisponible.",
                )

            message = payload.get("message", "").strip()

            if not message:
                return self.make_response(
                    False,
                    action,
                    error="Message vide.",
                )

            try:
                response = self.orchestrator.handle(message)

                return self.make_response(
                    True,
                    action,
                    {
                        "message": response,
                    },
                )

            except Exception as error:

                return self.make_response(
                    False,
                    action,
                    error=str(error),
                )

        # -----------------------------------------------------
        # ÉTAT
        # -----------------------------------------------------

        if action == "state":

            state = None

            if self.state_manager:
                state = self.state_manager.state.value

            return self.make_response(
                True,
                action,
                {
                    "state": state,
                },
            )

        return self.make_response(
            False,
            action,
            error=f"Action inconnue : {action}",
        )

    # =========================================================
    # BROADCAST
    # =========================================================

    async def broadcast(self, message):

        if not self.clients:
            return

        raw = json.dumps(
            message,
            ensure_ascii=False,
        )

        disconnected = set()

        for websocket in list(self.clients):

            try:
                await websocket.send(raw)

            except Exception:
                disconnected.add(websocket)

        self.clients.difference_update(disconnected)

    # =========================================================
    # CLIENT
    # =========================================================

    async def handle_client(self, websocket):

        print()
        print("📱 Connexion mobile entrante...")

        authorization = websocket.request.headers.get(
            "Authorization"
        )

        if TOKEN:

            expected = f"Bearer {TOKEN}"

            if authorization != expected:

                print("❌ Authentification mobile refusée.")

                await websocket.send(
                    json.dumps(
                        self.make_response(
                            False,
                            "authentication",
                            error="Token invalide.",
                        ),
                        ensure_ascii=False,
                    )
                )

                await websocket.close(
                    code=1008,
                    reason="Token invalide",
                )

                return

        self.clients.add(websocket)

        print("✅ Téléphone connecté.")

        try:

            await websocket.send(
                json.dumps(
                    {
                        "type": "connected",
                        "message": "JARVIS Mobile connecté.",
                    },
                    ensure_ascii=False,
                )
            )

            async for raw_message in websocket:

                try:
                    data = json.loads(raw_message)

                except json.JSONDecodeError:

                    await websocket.send(
                        json.dumps(
                            self.make_response(
                                False,
                                "unknown",
                                error="Message JSON invalide.",
                            ),
                            ensure_ascii=False,
                        )
                    )

                    continue

                action = data.get("action", "")
                payload = data.get("payload", {})

                if not isinstance(payload, dict):
                    payload = {}

                print(
                    f"📱 Mobile → {action}"
                )

                response = await self.execute_action(
                    action,
                    payload,
                )

                await websocket.send(
                    json.dumps(
                        response,
                        ensure_ascii=False,
                    )
                )

        except Exception as error:

            print(
                f"⚠️ Connexion mobile terminée : {error}"
            )

        finally:

            self.clients.discard(websocket)

            print("📴 Téléphone déconnecté.")

    # =========================================================
    # SERVEUR
    # =========================================================

    async def _run_server(self):

        self.loop = asyncio.get_running_loop()

        print()
        print("╔══════════════════════════════════════╗")
        print("║        JARVIS MOBILE BRIDGE         ║")
        print("╠══════════════════════════════════════╣")
        print(f"║ Adresse : {HOST}:{PORT:<21}║")
        print("║ WebSocket : actif                    ║")
        print(
            f"║ Authentification : "
            f"{'active' if TOKEN else 'désactivée':<15}║"
        )
        print("╚══════════════════════════════════════╝")
        print()

        async with serve(
            self.handle_client,
            HOST,
            PORT,
        ) as server:

            self.server = server
            self.running = True

            print("🚀 Serveur WebSocket démarré.")
            print("📱 En attente du téléphone...")
            print()

            await server.serve_forever()

    def _thread_target(self):

        try:
            asyncio.run(self._run_server())

        except Exception as error:

            self.running = False

            print(
                f"❌ Erreur serveur mobile : {error}"
            )

    # =========================================================
    # DÉMARRAGE
    # =========================================================

    def start(self):

        if self.running:
            print("⚠️ Le bridge mobile est déjà actif.")
            return

        self.thread = threading.Thread(
            target=self._thread_target,
            daemon=True,
        )

        self.thread.start()

    # =========================================================
    # ARRÊT
    # =========================================================

    def stop(self):

        if not self.running:
            return

        self.running = False

        if self.loop and self.server:

            self.loop.call_soon_threadsafe(
                self.server.close
            )

        self.server = None
        self.loop = None

        print("🛑 Bridge mobile arrêté.")


# =============================================================
# LANCEMENT DIRECT POUR TEST
# =============================================================

if __name__ == "__main__":

    bridge = MobileBridge()

    try:
        asyncio.run(bridge._run_server())

    except KeyboardInterrupt:

        print()
        print("🛑 Serveur mobile arrêté.")

