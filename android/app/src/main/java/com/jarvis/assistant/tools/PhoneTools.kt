package com.jarvis.assistant.tools

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.AlarmClock
import android.provider.ContactsContract
import android.provider.MediaStore
import android.telecom.TelecomManager
import android.telephony.SmsManager
import androidx.core.content.ContextCompat
import com.jarvis.assistant.JarvisSettings
import com.jarvis.assistant.access.WhatsAppService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.net.URLEncoder

/**
 * Actions directes sur le téléphone : applications, liens,
 * contacts, appels, SMS et WhatsApp.
 */
class PhoneTools(
    private val context: Context,
    private val settings: JarvisSettings,
) {

    private val packageManager = context.packageManager

    // Applications système dont le nom varie selon le fabricant :
    // on passe par une action Android standard.
    private val systemIntents: Map<String, () -> Intent> = mapOf(
        "appareil photo" to { Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA) },
        "camera" to { Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA) },
        "parametres" to { Intent(android.provider.Settings.ACTION_SETTINGS) },
        "reglages" to { Intent(android.provider.Settings.ACTION_SETTINGS) },
        "telephone" to { Intent(Intent.ACTION_DIAL) },
        "clavier" to { Intent(Intent.ACTION_DIAL) },
        "contacts" to { Intent(Intent.ACTION_VIEW, ContactsContract.Contacts.CONTENT_URI) },
        "messages" to { Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_MESSAGING) },
        "sms" to { Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_MESSAGING) },
        "calendrier" to { Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_CALENDAR) },
        "galerie" to { Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_GALLERY) },
        "calculatrice" to { Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_CALCULATOR) },
        "alarme" to { Intent(AlarmClock.ACTION_SHOW_ALARMS) },
        "reveil" to { Intent(AlarmClock.ACTION_SHOW_ALARMS) },
        "horloge" to { Intent(AlarmClock.ACTION_SHOW_ALARMS) },
    )

    // ========================================================
    // APPLICATIONS ET LIENS
    // ========================================================

    @Suppress("DEPRECATION")
    private fun launchableApps(): Map<String, String> {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val apps = LinkedHashMap<String, String>()

        for (info in packageManager.queryIntentActivities(intent, 0)) {
            apps.putIfAbsent(info.loadLabel(packageManager).toString(), info.activityInfo.packageName)
        }

        return apps
    }

    fun openApp(name: String): String {
        val key = Matching.normalize(name)
        val apps = launchableApps()

        // 1. Nom exact d'une application installée
        apps.entries.firstOrNull { Matching.normalize(it.key) == key }?.let {
            return launchPackage(it.key, it.value)
        }

        // 2. Application système (appareil photo, paramètres…)
        systemIntents[key]?.let {
            start(it())
            return "Application ouverte : $name"
        }

        // 3. Nom approché
        val label = Matching.best(name, apps.keys)
            ?: return "Application introuvable sur le téléphone : $name"

        return launchPackage(label, apps.getValue(label))
    }

    private fun launchPackage(label: String, packageName: String): String {
        val intent = packageManager.getLaunchIntentForPackage(packageName)
            ?: return "Impossible d'ouvrir $label."
        start(intent)
        return "Application ouverte : $label"
    }

    fun openLink(url: String): String {
        val target = if (Regex("^[a-zA-Z][a-zA-Z0-9+.-]*:").containsMatchIn(url)) url else "https://$url"
        start(Intent(Intent.ACTION_VIEW, Uri.parse(target)))
        return "Lien ouvert : $target"
    }

    fun searchYoutube(query: String): String =
        openLink("https://www.youtube.com/results?search_query=" + URLEncoder.encode(query, "UTF-8"))

    fun searchWeb(query: String): String =
        openLink("https://www.google.com/search?q=" + URLEncoder.encode(query, "UTF-8"))

    private fun start(intent: Intent) {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
    }

    // ========================================================
    // CONTACTS
    // ========================================================

    private fun requirePermission(permission: String, what: String) {
        if (ContextCompat.checkSelfPermission(context, permission) != PackageManager.PERMISSION_GRANTED) {
            throw IllegalStateException(
                "permission manquante pour $what. Ouvre les réglages de JARVIS et touche « Autoriser les permissions »."
            )
        }
    }

    private fun contacts(): Map<String, String> {
        requirePermission(Manifest.permission.READ_CONTACTS, "lire les contacts")

        val contacts = LinkedHashMap<String, String>()

        context.contentResolver.query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            arrayOf(
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                ContactsContract.CommonDataKinds.Phone.NUMBER,
            ),
            null,
            null,
            null,
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val name = cursor.getString(0) ?: continue
                val number = cursor.getString(1) ?: continue
                contacts.putIfAbsent(name, number)
            }
        }

        return contacts
    }

    private fun isNumber(text: String) = Regex("[+\\d][\\d\\s.\\-()]{5,}").matches(text.trim())

    private fun resolveContact(contact: String): Pair<String, String> {
        if (isNumber(contact)) return contact.trim() to contact.trim()

        val contacts = contacts()
        val name = Matching.best(contact, contacts.keys)
            ?: throw IllegalStateException("contact introuvable dans le téléphone : $contact")

        return name to contacts.getValue(name)
    }

    fun findContact(name: String): String {
        val wanted = Matching.normalize(name)
        val found = contacts().filterKeys { wanted in Matching.normalize(it) }

        if (found.isNotEmpty()) {
            return found.entries.take(20).joinToString("\n") { "${it.key} : ${it.value}" }
        }

        return try {
            val (contact, number) = resolveContact(name)
            "$contact : $number"
        } catch (e: IllegalStateException) {
            "Aucun contact ne correspond à « $name »."
        }
    }

    /** Format WhatsApp : indicatif + numéro, chiffres uniquement. */
    private fun international(number: String): String {
        val raw = number.trim()
        val digits = raw.filter { it.isDigit() }
        val code = settings.countryCode.filter { it.isDigit() }

        return when {
            raw.startsWith("+") -> digits
            digits.startsWith("00") -> digits.drop(2)
            code.isEmpty() -> digits
            digits.startsWith(code) && digits.length > 10 -> digits
            digits.startsWith("0") -> code + digits.drop(1)
            else -> code + digits
        }
    }

    // ========================================================
    // APPELS
    // ========================================================

    fun call(contact: String): String {
        requirePermission(Manifest.permission.CALL_PHONE, "passer des appels")

        val (name, number) = resolveContact(contact)
        start(Intent(Intent.ACTION_CALL, Uri.parse("tel:" + number.filter { it.isDigit() || it == '+' })))

        return "Appel en cours vers $name ($number)."
    }

    @Suppress("DEPRECATION", "MissingPermission")
    fun hangUp(): String {
        requirePermission(Manifest.permission.ANSWER_PHONE_CALLS, "gérer les appels")

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            return "Raccrocher automatiquement n'est pas possible sur cette version d'Android."
        }

        val telecom = context.getSystemService(TelecomManager::class.java)

        return if (telecom != null && telecom.endCall()) {
            "Appel terminé."
        } else {
            "Aucun appel à terminer, ou ce téléphone ne permet pas de raccrocher automatiquement."
        }
    }

    // ========================================================
    // MESSAGES
    // ========================================================

    suspend fun sendMessage(contact: String, message: String, service: String): String {
        val (name, number) = resolveContact(contact)

        return if (Matching.normalize(service) == "sms") {
            sendSms(name, number, message)
        } else {
            sendWhatsApp(name, number, message)
        }
    }

    @Suppress("DEPRECATION")
    private fun sendSms(name: String, number: String, message: String): String {
        requirePermission(Manifest.permission.SEND_SMS, "envoyer des SMS")

        val sms = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService(SmsManager::class.java)
        } else {
            SmsManager.getDefault()
        }

        sms.sendMultipartTextMessage(number, null, sms.divideMessage(message), null, null)

        return "SMS envoyé à $name ($number)."
    }

    private suspend fun sendWhatsApp(name: String, number: String, message: String): String {
        val packageName = settings.whatsappPackage
        val phone = international(number)
        val text = URLEncoder.encode(message, "UTF-8").replace("+", "%20")

        val intent = Intent(
            Intent.ACTION_VIEW,
            Uri.parse("https://api.whatsapp.com/send?phone=$phone&text=$text"),
        ).setPackage(packageName)

        if (!WhatsAppService.isEnabled(context)) {
            start(intent)
            return "WhatsApp est ouvert avec le message pour $name : il reste à appuyer sur Envoyer. " +
                "Pour que JARVIS envoie tout seul, active « JARVIS — envoi WhatsApp » dans ses réglages."
        }

        val request = WhatsAppService.arm(packageName)

        withContext(Dispatchers.Main) { start(intent) }

        // Le service appuie sur « Envoyer » dès que la conversation s'affiche.
        val sent = withTimeoutOrNull(15_000) {
            while (!request.isCompleted) {
                withContext(Dispatchers.Main) { WhatsAppService.tryClick() }
                delay(500)
            }
            request.await()
        } ?: false

        WhatsAppService.disarm()

        return if (sent) {
            "Message WhatsApp envoyé à $name."
        } else {
            "WhatsApp est ouvert avec le message pour $name, mais le bouton Envoyer n'a pas été trouvé " +
                "(ce numéro n'a peut-être pas WhatsApp)."
        }
    }
}
