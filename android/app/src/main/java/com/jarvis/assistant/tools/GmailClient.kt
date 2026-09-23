package com.jarvis.assistant.tools

import android.text.Html
import com.jarvis.assistant.JarvisSettings
import com.sun.mail.iap.Argument
import com.sun.mail.imap.IMAPFolder
import com.sun.mail.imap.protocol.IMAPProtocol
import com.sun.mail.imap.protocol.IMAPResponse
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.Properties
import javax.mail.FetchProfile
import javax.mail.Folder
import javax.mail.Message
import javax.mail.Multipart
import javax.mail.Part
import javax.mail.Session
import javax.mail.Transport
import javax.mail.internet.InternetAddress
import javax.mail.internet.MimeMessage

/**
 * Gmail via IMAP / SMTP avec un mot de passe d'application Google
 * (même principe que services/gmail.py sur le PC).
 */
class GmailClient(private val settings: JarvisSettings) {

    fun isConfigured(): Boolean =
        settings.gmailAddress.isNotBlank() && settings.gmailPassword.isNotBlank()

    private val address get() = settings.gmailAddress.trim()
    private val password get() = settings.gmailPassword.replace(" ", "")

    private fun requireConfigured() {
        check(isConfigured()) {
            "Gmail n'est pas configuré : ajoute ton adresse et ton mot de passe d'application dans les réglages de JARVIS."
        }
    }

    // ========================================================
    // LECTURE
    // ========================================================

    /**
     * Ouvre « Tous les messages » en lecture seule : un seul dossier pour
     * la boîte de réception et la recherche, donc des identifiants stables.
     */
    private fun <T> withMailbox(block: (IMAPFolder) -> T): T {
        requireConfigured()

        val properties = Properties().apply {
            put("mail.imaps.peek", "true")
            put("mail.imaps.connectiontimeout", "20000")
            put("mail.imaps.timeout", "30000")
        }

        val store = Session.getInstance(properties).getStore("imaps")
        store.connect("imap.gmail.com", address, password)

        try {
            val allMail = store.defaultFolder.list("*")
                .filterIsInstance<IMAPFolder>()
                .firstOrNull { folder -> folder.attributes.any { it.equals("\\All", ignoreCase = true) } }

            val folder = allMail ?: store.getFolder("INBOX") as IMAPFolder
            folder.open(Folder.READ_ONLY)

            try {
                return block(folder)
            } finally {
                folder.close(false)
            }
        } finally {
            store.close()
        }
    }

    /** Recherche avec la syntaxe Gmail (from:, is:unread, newer_than:7d…). */
    private fun searchUids(folder: IMAPFolder, query: String): List<Long> {
        val result = folder.doCommand { protocol: IMAPProtocol ->
            val args = Argument()
            args.writeAtom("CHARSET")
            args.writeAtom("UTF-8")
            args.writeAtom("X-GM-RAW")
            args.writeString(query, "UTF-8")

            val responses = protocol.command("UID SEARCH", args)
            val last = responses.last()
            val uids = ArrayList<Long>()

            if (last.isOK) {
                for (response in responses) {
                    if (response is IMAPResponse && response.keyEquals("SEARCH")) {
                        while (true) {
                            val uid = response.readLong()
                            if (uid < 0) break
                            uids.add(uid)
                        }
                    }
                }
            }

            protocol.notifyResponseHandlers(responses)
            protocol.handleResult(last)

            uids
        }

        @Suppress("UNCHECKED_CAST")
        return result as List<Long>
    }

    private fun summarize(folder: IMAPFolder, uids: List<Long>): String {
        if (uids.isEmpty()) return "Aucun e-mail trouvé."

        val messages = folder.getMessagesByUID(uids.toLongArray()).filterNotNull().toTypedArray()

        folder.fetch(messages, FetchProfile().apply { add(FetchProfile.Item.ENVELOPE) })

        val format = SimpleDateFormat("dd/MM HH:mm", Locale.FRANCE)

        return messages
            .sortedByDescending { folder.getUID(it) }
            .joinToString("\n") { message ->
                val sender = message.from?.firstOrNull()
                val from = (sender as? InternetAddress)?.let { it.personal ?: it.address } ?: sender?.toString() ?: "?"
                val date = (message.sentDate ?: message.receivedDate)?.let { format.format(it) } ?: ""
                "[id ${folder.getUID(message)}] $date — $from — ${message.subject ?: "(sans objet)"}"
            }
    }

    fun latest(count: Int, unreadOnly: Boolean): String = withMailbox { folder ->
        val query = if (unreadOnly) "in:inbox is:unread" else "in:inbox"
        summarize(folder, searchUids(folder, query).takeLast(count.coerceIn(1, 25)))
    }

    fun search(query: String, count: Int): String = withMailbox { folder ->
        summarize(folder, searchUids(folder, query).takeLast(count.coerceIn(1, 25)))
    }

    fun read(id: String): String = withMailbox { folder ->
        val uid = id.filter { it.isDigit() }.toLongOrNull()
            ?: return@withMailbox "Identifiant d'e-mail invalide : $id"

        val message = folder.getMessageByUID(uid)
            ?: return@withMailbox "E-mail introuvable : $id"

        val body = textOf(message).orEmpty()
            .replace(Regex("[ \\t]+"), " ")
            .replace(Regex("\\n\\s*\\n+"), "\n\n")
            .trim()
            .take(5000)

        buildString {
            append("De : ").append(addresses(message.from)).append('\n')
            append("À : ").append(addresses(message.getRecipients(Message.RecipientType.TO))).append('\n')
            append("Date : ").append(message.sentDate ?: "").append('\n')
            append("Sujet : ").append(message.subject ?: "(sans objet)").append("\n\n")
            append(body.ifEmpty { "(message vide)" })
        }
    }

    private fun addresses(list: Array<javax.mail.Address>?): String =
        list.orEmpty().joinToString { (it as? InternetAddress)?.toUnicodeString() ?: it.toString() }

    private fun textOf(part: Part): String? {
        if (Part.ATTACHMENT.equals(part.disposition, ignoreCase = true)) return null

        return when {
            part.isMimeType("text/plain") -> part.content as? String
            part.isMimeType("text/html") -> (part.content as? String)?.let { stripHtml(it) }
            part.isMimeType("multipart/*") -> {
                val multipart = part.content as Multipart
                val parts = (0 until multipart.count).map { multipart.getBodyPart(it) }

                parts.firstOrNull { it.isMimeType("text/plain") }?.let { textOf(it) }
                    ?: parts.firstNotNullOfOrNull { textOf(it) }
            }
            else -> null
        }
    }

    private fun stripHtml(html: String): String =
        Html.fromHtml(html, Html.FROM_HTML_MODE_COMPACT).toString()

    // ========================================================
    // ENVOI
    // ========================================================

    fun send(to: String, subject: String, body: String): String {
        requireConfigured()

        val properties = Properties().apply {
            put("mail.smtp.host", "smtp.gmail.com")
            put("mail.smtp.port", "465")
            put("mail.smtp.auth", "true")
            put("mail.smtp.ssl.enable", "true")
            put("mail.smtp.connectiontimeout", "20000")
            put("mail.smtp.timeout", "30000")
        }

        val message = MimeMessage(Session.getInstance(properties)).apply {
            setFrom(InternetAddress(address))
            setRecipients(Message.RecipientType.TO, InternetAddress.parse(to))
            setSubject(subject, "UTF-8")
            setText(body, "UTF-8")
        }

        Transport.send(message, address, password)

        return "E-mail envoyé à $to."
    }
}
