package com.jarvis.assistant.access

import android.accessibilityservice.AccessibilityService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.jarvis.assistant.MainActivity
import kotlinx.coroutines.CompletableDeferred

/**
 * Service d'accessibilité limité à WhatsApp : quand JARVIS vient
 * d'ouvrir une conversation avec un message pré-rempli, il appuie
 * sur « Envoyer », puis revient sur JARVIS. Il ne fait rien le
 * reste du temps.
 */
class WhatsAppService : AccessibilityService() {

    private val handler = Handler(Looper.getMainLooper())

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        clickSend()
    }

    override fun onInterrupt() {}

    private fun clickSend(): Boolean {
        val request = pending ?: return false
        val root = rootInActiveWindow ?: return false

        if (root.packageName?.toString() != request.packageName) return false

        val button = findSendButton(root, request.packageName) ?: return false

        if (!button.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return false

        pending = null
        request.result.complete(true)

        if (request.returnToApp) handler.postDelayed({ returnToJarvis() }, 700)

        return true
    }

    private fun findSendButton(root: AccessibilityNodeInfo, packageName: String): AccessibilityNodeInfo? {
        root.findAccessibilityNodeInfosByViewId("$packageName:id/send")
            .firstOrNull { it.isEnabled && it.isVisibleToUser }
            ?.let { return it }

        for (label in listOf("Envoyer", "Send")) {
            root.findAccessibilityNodeInfosByText(label)
                .firstOrNull { node ->
                    node.isClickable && node.isVisibleToUser &&
                        node.contentDescription?.toString().equals(label, ignoreCase = true)
                }
                ?.let { return it }
        }

        return null
    }

    private fun returnToJarvis() {
        startActivity(
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        )
    }

    private class Request(
        val packageName: String,
        val returnToApp: Boolean,
        val result: CompletableDeferred<Boolean>,
    )

    companion object {

        @Volatile
        private var instance: WhatsAppService? = null

        @Volatile
        private var pending: Request? = null

        fun isEnabled(context: Context): Boolean {
            val enabled = android.provider.Settings.Secure.getString(
                context.contentResolver,
                android.provider.Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            ) ?: return false

            val component = ComponentName(context, WhatsAppService::class.java)
            val names = setOf(component.flattenToString(), component.flattenToShortString())

            return enabled.split(':').any { entry -> names.any { it.equals(entry, ignoreCase = true) } }
        }

        fun arm(packageName: String, returnToApp: Boolean): CompletableDeferred<Boolean> {
            val result = CompletableDeferred<Boolean>()
            pending = Request(packageName, returnToApp, result)
            return result
        }

        fun disarm() {
            pending?.result?.complete(false)
            pending = null
        }

        fun tryClick(): Boolean = instance?.clickSend() ?: false
    }
}
