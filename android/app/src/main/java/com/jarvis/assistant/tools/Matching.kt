package com.jarvis.assistant.tools

import java.text.Normalizer

/**
 * Rapprochement tolérant entre ce que dit l'utilisateur et un nom
 * (application, contact) : « jean pierre » → « Jean-Pierre Dupont ».
 */
object Matching {

    private val accents = Regex("\\p{Mn}+")
    private val separators = Regex("[^\\p{L}\\p{N}+]+")
    private val spaces = Regex("\\s+")

    fun normalize(text: String): String {
        val withoutAccents = Normalizer.normalize(text, Normalizer.Form.NFD).replace(accents, "")
        return withoutAccents.lowercase().replace(separators, " ").trim().replace(spaces, " ")
    }

    fun best(query: String, candidates: Collection<String>, threshold: Double = 0.72): String? {
        val wanted = normalize(query)
        if (wanted.isEmpty()) return null

        val index = LinkedHashMap<String, String>()
        for (candidate in candidates) {
            index.putIfAbsent(normalize(candidate), candidate)
        }

        index[wanted]?.let { return it }

        // Mot entier, puis début du nom, puis n'importe où dans le nom.
        val rules = listOf<(String) -> Boolean>(
            { " $wanted " in " $it " },
            { it.startsWith(wanted) },
            { wanted.length >= 4 && wanted in it },
        )

        for (rule in rules) {
            val found = index.keys.filter(rule)
            if (found.isNotEmpty()) return index[found.minBy { it.length }]
        }

        var bestKey: String? = null
        var bestScore = 0.0

        for (key in index.keys) {
            val score = similarity(wanted, key)
            if (score > bestScore) {
                bestScore = score
                bestKey = key
            }
        }

        return if (bestScore >= threshold) index[bestKey] else null
    }

    private fun similarity(a: String, b: String): Double {
        val longest = maxOf(a.length, b.length)
        if (longest == 0) return 1.0
        return 1.0 - levenshtein(a, b).toDouble() / longest
    }

    private fun levenshtein(a: String, b: String): Int {
        var previous = IntArray(b.length + 1) { it }
        var current = IntArray(b.length + 1)

        for (i in 1..a.length) {
            current[0] = i
            for (j in 1..b.length) {
                val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                current[j] = minOf(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost)
            }
            val swap = previous
            previous = current
            current = swap
        }

        return previous[b.length]
    }
}
