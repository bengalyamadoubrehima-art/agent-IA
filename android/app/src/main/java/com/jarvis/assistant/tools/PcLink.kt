package com.jarvis.assistant.tools

import com.jarvis.assistant.JarvisSettings
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.withTimeout
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.TimeUnit

/**
 * Lien avec JARVIS sur le PC, via le serveur WebSocket de
 * mobile/server.py (port 8765, action « chat »).
 */
class PcLink(private val settings: JarvisSettings) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private fun hostAndPort(): Pair<String, Int>? {
        val raw = settings.pcAddress.trim()
            .removePrefix("ws://")
            .removePrefix("http://")
            .trimEnd('/')

        if (raw.isEmpty()) return null

        val host = raw.substringBefore(':')
        val port = raw.substringAfter(':', "").toIntOrNull() ?: 8765

        return host to port
    }

    fun reachable(): Boolean {
        val (host, port) = hostAndPort() ?: return false

        return try {
            Socket().use { it.connect(InetSocketAddress(host, port), 1500) }
            true
        } catch (e: Exception) {
            false
        }
    }

    suspend fun send(command: String): String {
        val (host, port) = hostAndPort()
            ?: return "Le PC n'est pas configuré : ajoute son adresse IP dans les réglages de JARVIS."

        val result = CompletableDeferred<String>()

        val request = Request.Builder()
            .url("ws://$host:$port")
            .apply {
                if (settings.pcToken.isNotBlank()) header("Authorization", "Bearer ${settings.pcToken}")
            }
            .build()

        val socket = client.newWebSocket(request, object : WebSocketListener() {

            override fun onOpen(webSocket: WebSocket, response: Response) {
                val message = JSONObject()
                    .put("action", "chat")
                    .put("payload", JSONObject().put("message", command))

                webSocket.send(message.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val data = try {
                    JSONObject(text)
                } catch (e: Exception) {
                    return
                }

                when (data.optString("action")) {
                    "chat" -> result.complete(
                        if (data.optBoolean("success")) {
                            data.optJSONObject("result")?.optString("message").orEmpty().ifBlank { "Fait sur le PC." }
                        } else {
                            "Le PC a répondu une erreur : ${data.optString("error")}"
                        }
                    )

                    "authentication" -> result.complete(
                        "Le PC a refusé la connexion : vérifie le jeton dans les réglages de JARVIS."
                    )
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                result.complete(
                    "PC injoignable (${t.message}). Vérifie qu'il est allumé, que JARVIS y tourne " +
                        "et que le téléphone est sur le même réseau."
                )
            }
        })

        return try {
            withTimeout(120_000) { result.await() }
        } catch (e: TimeoutCancellationException) {
            "Le PC n'a pas répondu à temps."
        } finally {
            socket.close(1000, null)
        }
    }
}
