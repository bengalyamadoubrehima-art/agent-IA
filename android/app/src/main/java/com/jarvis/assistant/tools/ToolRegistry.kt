package com.jarvis.assistant.tools

import org.json.JSONArray
import org.json.JSONObject

/**
 * Outils que l'IA peut utiliser sur le téléphone.
 * Les actions sensibles passent par une confirmation.
 */
class ToolRegistry(
    private val phone: PhoneTools,
    private val gmail: GmailClient,
    private val pc: PcLink,
    private val confirm: suspend (label: String, details: String) -> Boolean,
    private val log: (String) -> Unit,
) {

    private class Tool(
        val name: String,
        val label: String,
        val description: String,
        val parameters: JSONObject,
        val needsConfirmation: Boolean = false,
        val run: suspend (JSONObject) -> String,
    )

    private val tools = listOf(

        // ---------------- Applications et web ----------------

        Tool(
            "ouvrir_application", "Ouverture d'une application",
            "Ouvre une application du téléphone (youtube, whatsapp, instagram, appareil photo, paramètres…).",
            params("nom" to text(), required = listOf("nom")),
        ) { phone.openApp(it.optString("nom")) },

        Tool(
            "ouvrir_lien", "Ouverture d'un lien",
            "Ouvre un site ou un lien sur le téléphone.",
            params("url" to text(), required = listOf("url")),
        ) { phone.openLink(it.optString("url")) },

        Tool(
            "rechercher_youtube", "Recherche YouTube",
            "Lance une recherche dans YouTube sur le téléphone.",
            params("recherche" to text(), required = listOf("recherche")),
        ) { phone.searchYoutube(it.optString("recherche")) },

        Tool(
            "recherche_web", "Recherche web",
            "Lance une recherche Google sur le téléphone.",
            params("recherche" to text(), required = listOf("recherche")),
        ) { phone.searchWeb(it.optString("recherche")) },

        // ---------------- Contacts, appels, messages ----------------

        Tool(
            "rechercher_contact", "Recherche de contact",
            "Cherche un contact et son numéro dans le répertoire du téléphone.",
            params("nom" to text(), required = listOf("nom")),
        ) { phone.findContact(it.optString("nom")) },

        Tool(
            "appeler_contact", "Appel téléphonique",
            "Appelle un contact (nom du répertoire ou numéro).",
            params("contact" to text(), required = listOf("contact")),
            needsConfirmation = true,
        ) { phone.call(it.optString("contact")) },

        Tool(
            "raccrocher", "Fin d'appel",
            "Termine l'appel en cours.",
            params(),
        ) { phone.hangUp() },

        Tool(
            "envoyer_message", "Envoi d'un message",
            "Envoie un message à un contact (nom du répertoire ou numéro).",
            params(
                "contact" to text(),
                "message" to text(),
                "service" to text("whatsapp par défaut").put("enum", JSONArray(listOf("whatsapp", "sms"))),
                required = listOf("contact", "message"),
            ),
            needsConfirmation = true,
        ) { phone.sendMessage(it.optString("contact"), it.optString("message"), it.optString("service", "whatsapp")) },

        // ---------------- Gmail ----------------

        Tool(
            "lire_emails", "Lecture de Gmail",
            "Liste les derniers e-mails de la boîte de réception (expéditeur, sujet, id).",
            params(
                "nombre" to JSONObject().put("type", "integer").put("description", "5 par défaut, 25 maximum."),
                "non_lus_seulement" to JSONObject().put("type", "boolean"),
            ),
        ) { gmail.latest(it.optInt("nombre", 5), it.optBoolean("non_lus_seulement", false)) },

        Tool(
            "rechercher_emails", "Recherche dans Gmail",
            "Recherche des e-mails avec la syntaxe Gmail (from:banque, subject:facture, is:unread, newer_than:7d).",
            params(
                "recherche" to text(),
                "nombre" to JSONObject().put("type", "integer"),
                required = listOf("recherche"),
            ),
        ) { gmail.search(it.optString("recherche"), it.optInt("nombre", 10)) },

        Tool(
            "lire_email", "Lecture d'un e-mail",
            "Lit le contenu complet d'un e-mail à partir de son id.",
            params("identifiant" to text(), required = listOf("identifiant")),
        ) { gmail.read(it.optString("identifiant")) },

        Tool(
            "envoyer_email", "Envoi d'un e-mail",
            "Envoie un e-mail depuis le compte Gmail.",
            params(
                "destinataire" to text("Adresse e-mail."),
                "sujet" to text(),
                "contenu" to text(),
                required = listOf("destinataire", "sujet", "contenu"),
            ),
            needsConfirmation = true,
        ) { gmail.send(it.optString("destinataire"), it.optString("sujet"), it.optString("contenu")) },

        // ---------------- PC ----------------

        Tool(
            "commande_pc", "Commande envoyée au PC",
            "Transmet une demande à JARVIS sur l'ordinateur (ouvrir une application ou un fichier du PC, " +
                "VS Code, dossiers du PC…). Le PC doit être allumé avec JARVIS lancé.",
            params("commande" to text("La demande, formulée comme si l'utilisateur parlait au PC."), required = listOf("commande")),
        ) { pc.send(it.optString("commande")) },
    )

    /** Définitions au format « Chat Completions » (Gemini et OpenAI). */
    fun definitions(): JSONArray = JSONArray().apply {
        for (tool in tools) {
            put(
                JSONObject()
                    .put("type", "function")
                    .put(
                        "function",
                        JSONObject()
                            .put("name", tool.name)
                            .put("description", tool.description)
                            .put("parameters", tool.parameters)
                    )
            )
        }
    }

    suspend fun execute(name: String, arguments: JSONObject): String {
        val tool = tools.firstOrNull { it.name == name } ?: return "Outil inconnu : $name"

        if (tool.needsConfirmation) {
            val details = arguments.keys().asSequence()
                .joinToString("\n") { "$it : ${arguments.opt(it)}" }

            if (!confirm(tool.label, details)) {
                log("Refusé — ${tool.label}.")
                return "Action refusée par l'utilisateur."
            }
        }

        log("${tool.label}…")

        return try {
            tool.run(arguments)
        } catch (e: Exception) {
            val message = "Échec — ${tool.label} : ${e.message}"
            log(message)
            message
        }
    }

    private companion object {

        fun text(description: String? = null): JSONObject =
            JSONObject().put("type", "string").apply {
                if (description != null) put("description", description)
            }

        // Schéma volontairement simple : Gemini n'accepte qu'une partie de JSON Schema.
        fun params(vararg properties: Pair<String, JSONObject>, required: List<String> = emptyList()): JSONObject =
            JSONObject()
                .put("type", "object")
                .put("properties", JSONObject().apply { properties.forEach { (key, value) -> put(key, value) } })
                .apply { if (required.isNotEmpty()) put("required", JSONArray(required)) }
    }
}
