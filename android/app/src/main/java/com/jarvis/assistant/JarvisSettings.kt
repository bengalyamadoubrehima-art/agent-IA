package com.jarvis.assistant

import android.content.Context

/**
 * Réglages de JARVIS, stockés dans l'espace privé de l'application.
 */
class JarvisSettings(context: Context) {

    private val prefs = context.getSharedPreferences("jarvis", Context.MODE_PRIVATE)

    /** Cerveau utilisé : [PROVIDER_GEMINI] (gratuit, par défaut) ou [PROVIDER_OPENAI]. */
    var provider: String
        get() = text("provider", PROVIDER_GEMINI)
        set(value) = save("provider", value)

    var geminiKey: String
        get() = text("gemini_key")
        set(value) = save("gemini_key", value)

    var openAiKey: String
        get() = text("openai_key")
        set(value) = save("openai_key", value)

    /** Clé du cerveau choisi. */
    val apiKey: String
        get() = if (provider == PROVIDER_OPENAI) openAiKey else geminiKey

    /** Modèle imposé ; vide = choisi automatiquement. */
    var model: String
        get() = text("brain_model")
        set(value) = save("brain_model", value)

    var gmailAddress: String
        get() = text("gmail_address")
        set(value) = save("gmail_address", value)

    var gmailPassword: String
        get() = text("gmail_password")
        set(value) = save("gmail_password", value)

    var countryCode: String
        get() = text("country_code")
        set(value) = save("country_code", value.trim().removePrefix("+"))

    var whatsappPackage: String
        get() = text("whatsapp_package", "com.whatsapp")
        set(value) = save("whatsapp_package", value.ifBlank { "com.whatsapp" })

    var pcAddress: String
        get() = text("pc_address")
        set(value) = save("pc_address", value)

    var pcToken: String
        get() = text("pc_token")
        set(value) = save("pc_token", value)

    /** Écoute du mot « Jarvis » en arrière-plan. */
    var wakeEnabled: Boolean
        get() = prefs.getBoolean("wake_enabled", false)
        set(value) = prefs.edit().putBoolean("wake_enabled", value).apply()

    var speakReplies: Boolean
        get() = prefs.getBoolean("speak_replies", true)
        set(value) = prefs.edit().putBoolean("speak_replies", value).apply()

    private fun text(key: String, default: String = ""): String =
        prefs.getString(key, default) ?: default

    private fun save(key: String, value: String) {
        prefs.edit().putString(key, value.trim()).apply()
    }

    companion object {
        const val PROVIDER_GEMINI = "gemini"
        const val PROVIDER_OPENAI = "openai"

        // Modèle OpenAI par défaut (le même que sur le PC).
        const val DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
    }
}
