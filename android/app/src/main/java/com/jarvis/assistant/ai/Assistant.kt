package com.jarvis.assistant.ai

import com.jarvis.assistant.JarvisSettings
import com.jarvis.assistant.tools.ToolRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Cerveau de JARVIS : format « Chat Completions » avec appels d'outils,
 * compris par Google Gemini (gratuit, sans carte bancaire) et par OpenAI.
 */
class Assistant(
    private val settings: JarvisSettings,
    private val tools: ToolRegistry,
) {

    private val http = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    private val history = ArrayList<JSONObject>()

    // Modèle Gemini choisi automatiquement, mémorisé pour la clé en cours.
    private var geminiModel: String? = null
    private var geminiModelKey: String? = null

    suspend fun respond(message: String): String = withContext(Dispatchers.IO) {
        val provider = settings.provider
        val key = settings.apiKey

        if (key.isBlank()) {
            val name = if (provider == JarvisSettings.PROVIDER_OPENAI) "OpenAI" else "Gemini"
            return@withContext "Ajoute ta clé $name dans les réglages de JARVIS (icône en haut à droite)."
        }

        val model = resolveModel(provider, key)

        val messages = JSONArray()
        messages.put(JSONObject().put("role", "system").put("content", systemPrompt()))
        history.forEach { messages.put(it) }
        messages.put(JSONObject().put("role", "user").put("content", message))

        val definitions = tools.definitions()
        var answer: String? = null

        for (round in 0 until MAX_ROUNDS) {
            val reply = chat(provider, key, model, messages, definitions)
            val calls = reply.optJSONArray("tool_calls")

            if (calls == null || calls.length() == 0) {
                answer = if (reply.isNull("content")) "" else reply.optString("content")
                break
            }

            // L'appel d'outil doit être renvoyé tel quel avec son résultat.
            messages.put(
                JSONObject()
                    .put("role", "assistant")
                    .put("content", if (reply.isNull("content")) JSONObject.NULL else reply.optString("content"))
                    .put("tool_calls", calls)
            )

            for (i in 0 until calls.length()) {
                val call = calls.getJSONObject(i)
                val function = call.getJSONObject("function")

                val arguments = try {
                    JSONObject(function.optString("arguments", "{}").ifBlank { "{}" })
                } catch (e: Exception) {
                    JSONObject()
                }

                val result = tools.execute(function.getString("name"), arguments)

                messages.put(
                    JSONObject()
                        .put("role", "tool")
                        .put("tool_call_id", call.optString("id"))
                        .put("content", result)
                )
            }
        }

        val text = answer?.trim().orEmpty().ifBlank {
            if (answer == null) "Je n'ai pas pu terminer cette demande." else "Je n'ai pas de réponse."
        }

        remember("user", message)
        remember("assistant", text)

        text
    }

    private fun remember(role: String, content: String) {
        history.add(JSONObject().put("role", role).put("content", content))
        while (history.size > 16) history.removeAt(0)
    }

    // ========================================================
    // REQUÊTES
    // ========================================================

    private fun chat(
        provider: String,
        key: String,
        model: String,
        messages: JSONArray,
        definitions: JSONArray,
    ): JSONObject {
        val body = JSONObject()
            .put("model", model)
            .put("messages", messages)
            .put("tools", definitions)

        val request = Request.Builder()
            .url(baseUrl(provider) + "chat/completions")
            .header("Authorization", "Bearer $key")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val json = execute(request, provider)

        return json.getJSONArray("choices").getJSONObject(0).getJSONObject("message")
    }

    private fun execute(request: Request, provider: String): JSONObject {
        http.newCall(request).execute().use { response ->
            val text = response.body?.string().orEmpty()

            if (!response.isSuccessful) {
                throw IOException(describeError(provider, response.code, text))
            }

            return JSONObject(text)
        }
    }

    private fun describeError(provider: String, code: Int, body: String): String {
        val detail = try {
            val parsed = if (body.trimStart().startsWith("[")) JSONArray(body).getJSONObject(0) else JSONObject(body)
            parsed.optJSONObject("error")?.optString("message")
        } catch (e: Exception) {
            null
        } ?: body.take(300)

        val name = if (provider == JarvisSettings.PROVIDER_OPENAI) "OpenAI" else "Gemini"

        return when (code) {
            429 -> "$name : limite de demandes atteinte pour le moment, réessaie dans une minute. ($detail)"
            400, 401, 403 -> "$name refuse la demande : vérifie ta clé dans les réglages. ($detail)"
            404 -> "$name ne trouve pas le modèle : laisse le champ « Modèle » vide dans les réglages. ($detail)"
            else -> "$name ($code) : $detail"
        }
    }

    private fun baseUrl(provider: String): String =
        if (provider == JarvisSettings.PROVIDER_OPENAI) OPENAI_URL else GEMINI_URL

    // ========================================================
    // CHOIX DU MODÈLE
    // ========================================================

    private fun resolveModel(provider: String, key: String): String {
        settings.model.trim().takeIf { it.isNotEmpty() }?.let { return it }

        if (provider == JarvisSettings.PROVIDER_OPENAI) return JarvisSettings.DEFAULT_OPENAI_MODEL

        geminiModel?.takeIf { geminiModelKey == key }?.let { return it }

        val chosen = try {
            pickGeminiModel(key)
        } catch (e: Exception) {
            null
        } ?: GEMINI_FALLBACK

        geminiModel = chosen
        geminiModelKey = key

        return chosen
    }

    /**
     * Demande à Google les modèles disponibles pour cette clé et choisit
     * le « Flash » stable le plus récent (rapide et inclus dans l'offre gratuite).
     */
    private fun pickGeminiModel(key: String): String? {
        val request = Request.Builder()
            .url("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000")
            .header("x-goog-api-key", key)
            .build()

        val models = execute(request, JarvisSettings.PROVIDER_GEMINI).optJSONArray("models") ?: return null

        val names = (0 until models.length())
            .map { models.getJSONObject(it) }
            .filter { model ->
                val methods = model.optJSONArray("supportedGenerationMethods") ?: JSONArray()
                (0 until methods.length()).any { methods.optString(it) == "generateContent" }
            }
            .map { it.optString("name").removePrefix("models/") }
            .filter { it.startsWith("gemini-") && "flash" in it }

        return chooseGeminiModel(names)
    }

    private fun systemPrompt(): String {
        val now = SimpleDateFormat("EEEE d MMMM yyyy, HH:mm", Locale.FRANCE).format(Date())

        return """
            Tu es JARVIS, l'assistant personnel de l'utilisateur, installé sur son téléphone Android.
            Nous sommes le $now.

            Tu réponds en français, de façon naturelle, précise et concise. Tes réponses peuvent être
            lues à voix haute : pas de Markdown, pas de longues listes.

            Règles :
            - Ne prétends jamais avoir effectué une action si l'outil ne l'a pas réellement faite.
            - Utilise les outils dès qu'une action réelle est demandée.
            - Pour une action qui demande une confirmation, laisse le système de confirmation gérer la demande.

            Appareils :
            - Par défaut, agis sur ce téléphone.
            - Si l'utilisateur parle de son ordinateur ou de son PC (« ouvre VS Code sur le PC »),
              utilise commande_pc avec la demande reformulée.
            - Messages : WhatsApp par défaut, SMS seulement si demandé. Passe le nom du contact tel quel,
              il sera retrouvé dans le répertoire. Écris exactement le message demandé.
            - E-mails : liste d'abord (lire_emails ou rechercher_emails), puis ouvre avec l'id.
              Résume au lieu de tout recopier.
        """.trimIndent()
    }

    companion object {
        private const val MAX_ROUNDS = 8

        private const val GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
        private const val OPENAI_URL = "https://api.openai.com/v1/"
        private const val GEMINI_FALLBACK = "gemini-2.5-flash"

        private val EXCLUDED = listOf(
            "lite", "image", "tts", "audio", "live", "thinking", "exp", "embedding", "vision", "8b",
        )

        /** Choisit le meilleur modèle Flash : stable d'abord, puis version la plus récente. */
        fun chooseGeminiModel(names: List<String>): String? {
            val usable = names.filter { name -> EXCLUDED.none { it in name } }
            val stable = usable.filter { "preview" !in it && "latest" !in it }

            return (stable.ifEmpty { usable })
                .sortedWith(
                    compareByDescending<String> { version(it) }
                        .thenBy { it.length }
                )
                .firstOrNull()
        }

        private fun version(name: String): Double =
            Regex("gemini-(\\d+(?:\\.\\d+)?)").find(name)?.groupValues?.get(1)?.toDoubleOrNull() ?: 0.0
    }
}
