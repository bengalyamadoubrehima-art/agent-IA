package com.jarvis.assistant

/** Découpe un texte qui arrive par morceaux en phrases complètes, à dire une par une. */
class SentenceSplitter(private val maxLength: Int = 160) {

    private val buffer = StringBuilder()

    fun feed(text: String): List<String> {
        buffer.append(text)
        val sentences = ArrayList<String>()

        while (true) {
            val found = END.find(buffer) ?: break
            val sentence = buffer.substring(0, found.range.last + 1).trim()
            buffer.delete(0, found.range.last + 1)
            if (sentence.isNotEmpty()) sentences += sentence
        }

        // Phrase très longue : on coupe à la dernière virgule pour ne pas attendre.
        if (buffer.length > maxLength) {
            val cut = buffer.lastIndexOf(", ", maxLength)
            if (cut > 20) {
                sentences += buffer.substring(0, cut + 1).trim()
                buffer.delete(0, cut + 2)
            }
        }

        return sentences
    }

    fun flush(): String {
        val rest = buffer.toString().trim()
        buffer.clear()
        return rest
    }

    private companion object {
        val END = Regex("[.!?…]+[»\")]*\\s+|\n+")
    }
}
