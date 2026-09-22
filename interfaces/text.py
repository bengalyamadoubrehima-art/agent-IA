class TextInterface:

    def __init__(self, orchestrator, voice=None):
        self.orchestrator = orchestrator
        self.voice = voice

    def run(self):

        print()
        print("╔══════════════════════════════════╗")
        print("║             JARVIS               ║")
        print("╠══════════════════════════════════╣")
        print("║ Texte : actif                    ║")
        print("║ Voix  : active                   ║")
        print("╚══════════════════════════════════╝")
        print()

        print("Commandes :")
        print("  /voice  → parler à Jarvis")
        print("  /quit   → arrêter")
        print()

        while True:

            try:
                message = input("Toi > ").strip()

            except (KeyboardInterrupt, EOFError):
                print()
                print("Jarvis > Arrêt.")
                break

            if not message:
                continue

            command = message.lower()

            if command in {
                "/quit",
                "quitter",
                "exit",
                "quit",
            }:
                print()
                print("Jarvis > Arrêt.")
                break

            if command == "/voice":

                if self.voice is None:
                    print(
                        "Jarvis > L'interface vocale n'est pas disponible."
                    )
                    continue

                print()
                print("🎙️ Mode vocal")
                print()

                self.voice.process_once()

                print()
                continue

            try:
                response = self.orchestrator.handle(message)

                print()
                print(f"Jarvis > {response}")
                print()

            except Exception as error:
                print()
                print(f"❌ Erreur : {error}")
                print()