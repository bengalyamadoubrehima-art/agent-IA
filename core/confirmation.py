class ConfirmationService:
    """
    Gestion des confirmations utilisateur
    pour les actions sensibles.
    """

    def ask(
        self,
        tool_name,
        arguments
    ):

        print()
        print("╔══════════════════════════════════════╗")
        print("║       ⚠️  CONFIRMATION REQUISE       ║")
        print("╚══════════════════════════════════════╝")

        print()
        print(f"Action : {tool_name}")

        if arguments:
            print(
                f"Détails : {arguments}"
            )

        print()

        while True:

            answer = input(
                "Confirmer ? [o/n] : "
            ).strip().lower()

            if answer in {
                "o",
                "oui",
                "y",
                "yes",
            }:

                print(
                    "✅ Action confirmée."
                )

                return True

            if answer in {
                "n",
                "non",
                "no",
            }:

                print(
                    "❌ Action annulée."
                )

                return False

            print(
                "Réponds par o ou n."
            )