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
 * Cerveau de JARVIS : API Responses d'OpenAI avec appels d'outils,
 * comme core/ai.py sur le PC.
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

    suspend fun respond(message: String): String = withContext(Dispatchers.IO) {
        if (settings.openAiKey.isBlank()) {
            return@withContext "Ajoute ta clé OpenAI dans les réglages de JARVIS (icône en haut à droite)."
        }

        val input = JSONArray()
        input.put(JSONObject().put("role", "developer").put("content", systemPrompt()))
        history.forEach { input.put(it) }
        input.put(JSONObject().put("role", "user").put("content", message))

        val definitions = tools.definitions()

        var response = post(
            JSONObject()
                .put("model", settings.model)
                .put("input", input)
                .put("tools", definitions)
        )

        for (round in 0 until 8) {
            val calls = functionCalls(response)
            if (calls.isEmpty()) break

            val outputs = JSONArray()

            for (call in calls) {
                val arguments = try {
                    JSONObject(call.optString("arguments", "{}"))
                } catch (e: Exception) {
                    JSONObject()
                }

                val result = tools.execute(call.getString("name"), arguments)

                outputs.put(
                    JSONObject()
                        .put("type", "function_call_output")
                        .put("call_id", call.getString("call_id"))
                        .put("output", result)
                )
            }

            response = post(
                JSONObject()
                    .put("model", settings.model)
                    .put("previous_response_id", response.getString("id"))
                    .put("input", outputs)
                    .put("tools", definitions)
            )
        }

        val answer = outputText(response).ifBlank { "Je n'ai pas de réponse." }

        remember("user", message)
        remember("assistant", answer)

        answer
    }

    private fun remember(role: String, content: String) {
        history.add(JSONObject().put("role", role).put("content", content))
        while (history.size > 16) history.removeAt(0)
    }

    private fun post(body: JSONObject): JSONObject {
        val request = Request.Builder()
            .url("https://api.openai.com/v1/responses")
            .header("Authorization", "Bearer ${settings.openAiKey}")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        http.newCall(request).execute().use { response ->
            val text = response.body?.string().orEmpty()

            if (!response.isSuccessful) {
                val detail = try {
                    JSONObject(text).optJSONObject("error")?.optString("message")
                } catch (e: Exception) {
                    null
                }
                throw IOException("OpenAI (${response.code}) : ${detail ?: text.take(300)}")
            }

            return JSONObject(text)
        }
    }

    private fun functionCalls(response: JSONObject): List<JSONObject> {
        val output = response.optJSONArray("output") ?: return emptyList()
        return (0 until output.length())
            .map { output.getJSONObject(it) }
            .filter { it.optString("type") == "function_call" }
    }

    private fun outputText(response: JSONObject): String {
        val output = response.optJSONArray("output") ?: return ""
        val text = StringBuilder()

        for (i in 0 until output.length()) {
            val item = output.getJSONObject(i)
            if (item.optString("type") != "message") continue

            val content = item.optJSONArray("content") ?: continue
            for (j in 0 until content.length()) {
                val part = content.getJSONObject(j)
                if (part.optString("type") == "output_text") text.append(part.optString("text"))
            }
        }

        return text.toString().trim()
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
}
