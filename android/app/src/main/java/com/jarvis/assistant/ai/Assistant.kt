package com.jarvis.assistant.ai

import com.jarvis.assistant.JarvisSettings
import com.jarvis.assistant.tools.ToolRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * Cerveau de JARVIS : format « Chat Completions » avec appels d'outils,
 * compris par Google Gemini et Groq (gratuits, sans carte bancaire) et par OpenAI.
 *
 * Les réponses arrivent en continu (streaming) : la première phrase est
 * affichée et dite pendant que la suite s'écrit.
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

    // Modèle choisi automatiquement, mémorisé pour le fournisseur et la clé en cours.
    private var chosenModel: String? = null
    private var chosenFor: String? = null

    // Autres modèles gratuits, utilisés quand le principal est saturé.
    private var backups: List<String> = emptyList()

    private var reasoningSupported = true

    @Volatile
    private var lastNetwork = 0L

    /** Erreur HTTP de l'API, avec son code pour décider s'il faut réessayer. */
    private class ApiException(val code: Int, message: String) : IOException(message)

    /**
     * Répond à un message. [onText] reçoit la réponse morceau par morceau
     * (depuis un thread d'arrière-plan).
     */
    suspend fun respond(message: String, onText: (String) -> Unit = {}): String = withContext(Dispatchers.IO) {
        val provider = settings.provider
        val key = settings.apiKey

        if (key.isBlank()) {
            val name = JarvisSettings.providerName(provider)
            return@withContext "Ajoute ta clé $name dans les réglages de JARVIS (icône en haut à droite)."
        }

        val model = resolveModel(provider, key)

        val messages = JSONArray()
        messages.put(JSONObject().put("role", "system").put("content", systemPrompt()))
        history.forEach { messages.put(it) }
        messages.put(JSONObject().put("role", "user").put("content", message))

        val definitions = tools.definitions()
        val parts = StringBuilder()
        var finished = false

        for (round in 0 until MAX_ROUNDS) {
            var newRound = true

            val reply = chatWithFallback(provider, key, model, messages, definitions) { chunk ->
                // Espace entre le texte de deux tours (annonce puis confirmation).
                val text = if (newRound && parts.isNotEmpty()) " " + chunk.trimStart() else chunk
                newRound = false
                parts.append(text)
                onText(text)
            }

            val calls = reply.optJSONArray("tool_calls")

            if (calls == null || calls.length() == 0) {
                finished = true
                break
            }

            // L'appel d'outil est renvoyé tel quel (avec la « thought_signature »
            // de Gemini), suivi de son résultat.
            messages.put(reply)

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

        val text = parts.toString().trim().ifBlank {
            if (finished) "Je n'ai pas de réponse." else "Je n'ai pas pu terminer cette demande."
        }

        remember("user", message)
        remember("assistant", text)

        text
    }

    /**
     * À appeler dès que l'utilisateur commence à parler : choisit le modèle et
     * rouvre la connexion si elle dort, pendant qu'il parle encore.
     */
    suspend fun warmUp(): Unit = withContext(Dispatchers.IO) {
        val provider = settings.provider
        val key = settings.apiKey
        if (key.isBlank()) return@withContext

        try {
            val fresh = chosenFor != provider + key
            resolveModel(provider, key)

            if (!fresh && System.currentTimeMillis() - lastNetwork > IDLE_MS) {
                val url = if (provider == JarvisSettings.PROVIDER_GEMINI) {
                    "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
                } else {
                    baseUrl(provider) + "models"
                }

                execute(authorized(Request.Builder().url(url), provider, key).build(), provider)
            }
        } catch (e: Exception) {
            // Simple préchauffage : la vraie requête affichera l'erreur éventuelle.
        }

        Unit
    }

    private fun remember(role: String, content: String) {
        history.add(JSONObject().put("role", role).put("content", content))
        while (history.size > 16) history.removeAt(0)
    }

    // ========================================================
    // REQUÊTES
    // ========================================================

    /**
     * Les services gratuits sont parfois saturés (503) ou limités (429) : on
     * patiente un instant, puis on essaie les autres modèles gratuits.
     */
    private fun chatWithFallback(
        provider: String,
        key: String,
        model: String,
        messages: JSONArray,
        definitions: JSONArray,
        onText: (String) -> Unit,
    ): JSONObject {
        val automatic = provider != JarvisSettings.PROVIDER_OPENAI && settings.model.isBlank()

        val attempts = buildList {
            add(model)
            add(model)
            if (automatic) addAll(backups.filter { it != model })
        }

        var lastError: ApiException? = null

        for ((index, candidate) in attempts.withIndex()) {
            val response = try {
                openStream(provider, key, candidate, messages, definitions)
            } catch (e: ApiException) {
                if (!switchable(provider, e)) throw e
                lastError = e
                if (index < attempts.lastIndex) Thread.sleep(if (index == 0) 1000L else 300L)
                continue
            }

            return readStream(response, onText)
        }

        throw lastError ?: IOException("Pas de réponse.")
    }

    private fun switchable(provider: String, error: ApiException): Boolean =
        error.code in RETRYABLE ||
            // Groq : appel d'outil mal formé par le modèle, un autre peut réussir.
            (provider == JarvisSettings.PROVIDER_GROQ && error.code == 400 &&
                error.message.orEmpty().contains("tool_use_failed"))

    private fun openStream(
        provider: String,
        key: String,
        model: String,
        messages: JSONArray,
        definitions: JSONArray,
    ): Response {
        val body = JSONObject()
            .put("model", model)
            .put("messages", messages)
            .put("tools", definitions)
            .put("stream", true)

        val effort = reasoningEffort(provider, model)?.takeIf { reasoningSupported }
        if (effort != null) body.put("reasoning_effort", effort)

        fun request() = authorized(Request.Builder(), provider, key)
            .url(baseUrl(provider) + "chat/completions")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        return try {
            open(request(), provider)
        } catch (e: ApiException) {
            // Réglage refusé par ce modèle : on réessaie sans.
            if (effort == null || e.code != 400) throw e
            body.remove("reasoning_effort")
            open(request(), provider).also { reasoningSupported = false }
        }
    }

    /** Lit la réponse au fil de l'eau et renvoie le message complet de l'assistant. */
    private fun readStream(response: Response, onText: (String) -> Unit): JSONObject {
        val text = StringBuilder()
        val calls = ArrayList<JSONObject>()
        val byIndex = HashMap<Int, JSONObject>()

        response.use {
            val source = response.body!!.source()

            while (true) {
                val line = source.readUtf8Line() ?: break
                if (!line.startsWith("data:")) continue

                val data = line.removePrefix("data:").trim()
                if (data == "[DONE]") break
                if (data.isEmpty()) continue

                val chunk = JSONObject(data)
                chunk.optJSONObject("error")?.let { error ->
                    throw ApiException(error.optInt("code", 500), error.optString("message"))
                }

                val delta = chunk.optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("delta") ?: continue

                if (delta.has("content") && !delta.isNull("content")) {
                    val piece = delta.optString("content")
                    if (piece.isNotEmpty()) {
                        text.append(piece)
                        onText(piece)
                    }
                }

                val parts = delta.optJSONArray("tool_calls") ?: continue

                for (i in 0 until parts.length()) {
                    val part = parts.getJSONObject(i)
                    val index = if (part.has("index")) part.optInt("index") else null
                    val id = part.optString("id")

                    val found = (if (index != null) byIndex[index] else calls.lastOrNull())
                        // Un nouvel identifiant = un nouvel appel.
                        ?.takeUnless { id.isNotEmpty() && it.optString("id").let { old -> old.isNotEmpty() && old != id } }

                    val current: JSONObject = found ?: JSONObject()
                        .put("id", "")
                        .put("type", "function")
                        .put("function", JSONObject().put("name", "").put("arguments", ""))
                        .also { created ->
                            calls += created
                            if (index != null) byIndex[index] = created
                        }

                    part.optJSONObject("function")?.let { function ->
                        val target = current.getJSONObject("function")
                        function.optString("name").takeIf { it.isNotEmpty() }?.let { target.put("name", it) }
                        function.optString("arguments").takeIf { it.isNotEmpty() }?.let {
                            target.put("arguments", target.optString("arguments") + it)
                        }
                    }

                    // id, type et champs propres au fournisseur (ex. extra_content de Gemini).
                    for (field in part.keys()) {
                        if (field == "index" || field == "function") continue
                        val value = part.get(field)
                        if (value != JSONObject.NULL && value.toString().isNotEmpty()) current.put(field, value)
                    }
                }
            }
        }

        lastNetwork = System.currentTimeMillis()

        val message = JSONObject()
            .put("role", "assistant")
            .put("content", if (text.isEmpty()) JSONObject.NULL else text.toString())

        if (calls.isNotEmpty()) {
            calls.forEachIndexed { number, call ->
                if (call.optString("id").isEmpty()) call.put("id", "call_$number")
                val function = call.getJSONObject("function")
                if (function.optString("arguments").isBlank()) function.put("arguments", "{}")
            }
            message.put("tool_calls", JSONArray(calls))
        }

        return message
    }

    private fun authorized(builder: Request.Builder, provider: String, key: String): Request.Builder =
        if (provider == JarvisSettings.PROVIDER_GEMINI) {
            builder.header("Authorization", "Bearer $key").header("x-goog-api-key", key)
        } else {
            builder.header("Authorization", "Bearer $key")
        }

    /** Ouvre la requête ; lève une [ApiException] si le serveur refuse. */
    private fun open(request: Request, provider: String): Response {
        val response = http.newCall(request).execute()

        if (!response.isSuccessful) {
            val text = response.use { it.body?.string().orEmpty() }
            throw ApiException(response.code, describeError(provider, response.code, text))
        }

        return response
    }

    private fun execute(request: Request, provider: String): JSONObject =
        open(request, provider).use { response ->
            lastNetwork = System.currentTimeMillis()
            JSONObject(response.body?.string().orEmpty())
        }

    private fun describeError(provider: String, code: Int, body: String): String {
        val detail = try {
            val parsed = if (body.trimStart().startsWith("[")) JSONArray(body).getJSONObject(0) else JSONObject(body)
            parsed.optJSONObject("error")?.optString("message")
        } catch (e: Exception) {
            null
        } ?: body.take(300)

        val name = JarvisSettings.providerName(provider)

        return when (code) {
            429 -> "$name : limite de demandes atteinte pour le moment, réessaie dans une minute. ($detail)"
            500, 502, 503, 504 -> "$name est surchargé en ce moment (trop de monde l'utilise). Réessaie dans quelques secondes."
            400, 401, 403 -> "$name refuse la demande : vérifie ta clé dans les réglages. ($detail)"
            404 -> "$name ne trouve pas le modèle : laisse le champ « Modèle » vide dans les réglages. ($detail)"
            else -> "$name ($code) : $detail"
        }
    }

    private fun baseUrl(provider: String): String = when (provider) {
        JarvisSettings.PROVIDER_OPENAI -> OPENAI_URL
        JarvisSettings.PROVIDER_GROQ -> GROQ_URL
        else -> GEMINI_URL
    }

    // ========================================================
    // CHOIX DU MODÈLE
    // ========================================================

    @Synchronized
    private fun resolveModel(provider: String, key: String): String {
        settings.model.trim().takeIf { it.isNotEmpty() }?.let { return it }

        if (provider == JarvisSettings.PROVIDER_OPENAI) return JarvisSettings.DEFAULT_OPENAI_MODEL

        chosenModel?.takeIf { chosenFor == provider + key }?.let { return it }

        val chosen = try {
            if (provider == JarvisSettings.PROVIDER_GROQ) pickGroqModel(key) else pickGeminiModel(key)
        } catch (e: Exception) {
            null
        }

        if (chosen == null) {
            backups = if (provider == JarvisSettings.PROVIDER_GROQ) emptyList() else GEMINI_BACKUPS
        }

        val model = chosen ?: if (provider == JarvisSettings.PROVIDER_GROQ) GROQ_FALLBACK else GEMINI_FALLBACK

        chosenModel = model
        chosenFor = provider + key
        reasoningSupported = true

        return model
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

        backups = backupModels(names).ifEmpty { GEMINI_BACKUPS }

        return chooseGeminiModel(names)
    }

    /** Demande à Groq ses modèles et prend le meilleur de la liste de préférence. */
    private fun pickGroqModel(key: String): String? {
        val request = authorized(Request.Builder(), JarvisSettings.PROVIDER_GROQ, key)
            .url(GROQ_URL + "models")
            .build()

        val data = execute(request, JarvisSettings.PROVIDER_GROQ).optJSONArray("data") ?: return null
        val ranked = groqModels((0 until data.length()).map { data.getJSONObject(it).optString("id") })

        backups = ranked.drop(1).take(3)

        return ranked.firstOrNull()
    }

    private fun systemPrompt(): String {
        val now = SimpleDateFormat("EEEE d MMMM yyyy, HH:mm", Locale.FRANCE).format(Date())

        return """
            Tu es JARVIS, l'assistant personnel de l'utilisateur, installé sur son téléphone Android.
            Nous sommes le $now.

            Tu réponds en français, de façon naturelle, précise et concise : une à trois phrases, sauf si
            l'utilisateur demande des détails. Tes réponses sont souvent lues à voix haute : pas de Markdown,
            pas de longues listes.

            Rapidité :
            - Quand tu lances une action avec un outil, écris dans le même message une très courte phrase
              qui l'annonce (« J'ouvre YouTube. »).
            - Si la demande contient plusieurs actions indépendantes, appelle tous les outils nécessaires
              en même temps, pas l'un après l'autre.
            - Après une action réussie, confirme en quelques mots seulement.

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
        private const val GROQ_URL = "https://api.groq.com/openai/v1/"
        private const val OPENAI_URL = "https://api.openai.com/v1/"
        private const val GEMINI_FALLBACK = "gemini-2.5-flash"
        private const val GROQ_FALLBACK = "llama-3.3-70b-versatile"

        private val GEMINI_BACKUPS = listOf("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash")

        /** Modèles Groq, du préféré au moins bon : bons en français et avec les outils. */
        private val GROQ_PREFERRED = listOf(
            "openai/gpt-oss-120b",
            "llama-3.3-70b-versatile",
            "moonshotai/kimi-k2-instruct",
            "meta-llama/llama-4-maverick",
            "qwen/qwen3-32b",
            "openai/gpt-oss-20b",
            "meta-llama/llama-4-scout",
        )

        private val GROQ_EXCLUDED = listOf("guard", "whisper", "tts", "playai", "compound", "orpheus", "safeguard")

        private val RETRYABLE = setOf(429, 500, 502, 503, 504)

        /** Au-delà, la connexion est rafraîchie pendant que l'utilisateur parle. */
        private const val IDLE_MS = 45_000L

        fun groqModels(names: List<String>): List<String> {
            val usable = names.filter { name -> GROQ_EXCLUDED.none { it in name } }
            val ranked = LinkedHashSet<String>()

            for (prefix in GROQ_PREFERRED) {
                usable.sortedDescending().filter { it.startsWith(prefix) }.forEach { ranked += it }
            }

            return ranked.toList()
        }

        /**
         * Beaucoup de modèles « réfléchissent » en silence avant de répondre, ce qui
         * ajoute plusieurs secondes : on réduit cette réflexion au minimum.
         */
        fun reasoningEffort(provider: String, model: String): String? = when (provider) {
            JarvisSettings.PROVIDER_GEMINI -> if (model.startsWith("gemini-2")) "none" else "minimal"
            JarvisSettings.PROVIDER_GROQ -> when {
                "gpt-oss" in model -> "low"
                "qwen3" in model -> "none"
                else -> null
            }
            else -> null
        }

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

        /** Modèles de secours : les Flash stables récents, puis les « lite » (au plus 4). */
        fun backupModels(names: List<String>): List<String> {
            val usable = names.filter { name ->
                EXCLUDED.filter { it != "lite" }.none { it in name } && "preview" !in name && "latest" !in name
            }

            return usable
                .sortedWith(
                    compareBy<String> { "lite" in it }
                        .thenByDescending { version(it) }
                        .thenBy { it.length }
                )
                .take(4)
        }

        private fun version(name: String): Double =
            Regex("gemini-(\\d+(?:\\.\\d+)?)").find(name)?.groupValues?.get(1)?.toDoubleOrNull() ?: 0.0
    }
}
