package com.jarvis.assistant

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale

/**
 * Voix de JARVIS avec les services Android (gratuits) :
 * reconnaissance vocale et synthèse vocale en français.
 */
class Voice(
    private val context: Context,
    private val listener: Listener,
) {

    interface Listener {
        fun onPartial(text: String)
        fun onFinal(text: String)
        fun onLevel(level: Float)
        fun onListenError(message: String)
        fun onSpeakingDone()
    }

    private val main = Handler(Looper.getMainLooper())
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false

    val canListen: Boolean
        get() = SpeechRecognizer.isRecognitionAvailable(context)

    val canSpeak: Boolean
        get() = ttsReady

    init {
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale.FRANCE) ?: TextToSpeech.LANG_NOT_SUPPORTED
                ttsReady = result >= TextToSpeech.LANG_AVAILABLE
            }
        }

        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}

            override fun onDone(utteranceId: String?) {
                main.post { listener.onSpeakingDone() }
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                main.post { listener.onSpeakingDone() }
            }
        })
    }

    // ========================================================
    // ÉCOUTE
    // ========================================================

    private val recognitionListener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onEvent(eventType: Int, params: Bundle?) {}

        override fun onRmsChanged(rmsdB: Float) {
            listener.onLevel(((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
        }

        override fun onPartialResults(partialResults: Bundle?) {
            firstResult(partialResults)?.let { listener.onPartial(it) }
        }

        override fun onResults(results: Bundle?) {
            val text = firstResult(results)
            if (text.isNullOrBlank()) {
                listener.onListenError("Je n'ai rien entendu.")
            } else {
                listener.onFinal(text)
            }
        }

        override fun onError(error: Int) {
            listener.onListenError(
                when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH,
                    SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Je n'ai rien entendu."
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Autorise le micro dans les réglages de JARVIS."
                    SpeechRecognizer.ERROR_NETWORK,
                    SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Reconnaissance vocale : pas de connexion."
                    SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Le micro est déjà utilisé, réessaie."
                    SpeechRecognizer.ERROR_CLIENT -> "Écoute arrêtée."
                    else -> "Erreur du micro (code $error)."
                }
            )
        }
    }

    private fun firstResult(bundle: Bundle?): String? =
        bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()

    fun listen() {
        val current = recognizer ?: SpeechRecognizer.createSpeechRecognizer(context).also {
            it.setRecognitionListener(recognitionListener)
            recognizer = it
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
        }

        current.startListening(intent)
    }

    fun stopListening() {
        recognizer?.stopListening()
    }

    // ========================================================
    // PAROLE
    // ========================================================

    fun speak(text: String) {
        val result = tts?.speak(clean(text), TextToSpeech.QUEUE_FLUSH, null, "jarvis-${System.nanoTime()}")

        if (result != TextToSpeech.SUCCESS) {
            main.post { listener.onSpeakingDone() }
        }
    }

    fun stopSpeaking() {
        tts?.stop()
    }

    private fun clean(text: String): String =
        text.replace(Regex("https?://\\S+"), "le lien")
            .replace(Regex("[*#_`>]"), "")
            .replace(Regex("\\s+"), " ")
            .trim()

    fun release() {
        recognizer?.destroy()
        recognizer = null
        tts?.shutdown()
        tts = null
    }
}
