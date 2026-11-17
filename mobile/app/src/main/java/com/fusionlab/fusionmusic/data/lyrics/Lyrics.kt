package com.fusionlab.fusionmusic.data.lyrics

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

data class LyricWord(
    var text: String,
    var start: Int,
    var duration: Int,
    var charStart: Int = 0,
    var charEnd: Int = 0
) {
    val end: Int get() = start + duration
}

data class LyricLine(
    var text: String,
    var time: Int,
    var translation: String = "",
    var roma: String = "",
    var words: MutableList<LyricWord> = mutableListOf(),
    var wordSource: String = ""
) {
    val isWordBased: Boolean get() = words.isNotEmpty()
    val endTime: Int get() = words.lastOrNull()?.end ?: (time + Lyrics.DEFAULT_LINE_MS)
    val hasSub: Boolean get() = translation.isNotBlank() || roma.isNotBlank()
    val subText: String get() = translation.ifBlank { roma }
}

class Lyrics {
    val lines: MutableList<LyricLine> = mutableListOf()
    val tags: MutableMap<String, String> = mutableMapOf()
    var offsetMs: Int = 0
    private var times: MutableList<Int> = mutableListOf()
    private var cacheKey: Int = -10000
    private var cacheIndex: Int = -1

    val isEmpty: Boolean get() = lines.isEmpty()

    fun clear() {
        lines.clear()
        tags.clear()
        offsetMs = 0
        times.clear()
        cacheKey = -10000
        cacheIndex = -1
    }

    fun parse(rawText: String?): Boolean {
        clear()
        if (rawText.isNullOrBlank()) return false
        for (line in rawText.split("\n")) {
            for (match in META_TAG_RE.findAll(line)) {
                tags[match.groupValues[1].lowercase()] = match.groupValues[2]
            }
        }
        offsetMs = tags["offset"]?.toDoubleOrNull()?.toInt() ?: 0
        for (line in rawText.split("\n")) {
            lines.addAll(parseLine(line))
        }
        lines.sortBy { it.time }
        rebuildTimes()
        return lines.isNotEmpty()
    }

    fun setTranslation(raw: String?) = merge(raw, true)

    fun setRoma(raw: String?) = merge(raw, false)

    fun setWords(raw: String?): Int {
        if (raw.isNullOrBlank() || lines.isEmpty()) return 0
        val sub = Lyrics()
        sub.parse(raw)
        val candidates = sub.lines.filter { it.words.isNotEmpty() }
        if (candidates.isEmpty()) return 0
        val shift = offsetMs - sub.offsetMs
        if (shift != 0) {
            for (line in candidates) line.time = max(0, line.time + shift)
        }
        val lookup = LinkedHashMap<Int, LyricLine>()
        for (line in candidates) lookup.putIfAbsent(line.time, line)
        val ordered = lookup.keys.sorted()
        var matched = 0
        for (line in lines) {
            if (line.words.isNotEmpty()) continue
            var candidate = lookup[line.time]
            if (candidate == null || normalizeText(candidate.text) != normalizeText(line.text)) {
                candidate = nearest(lookup, ordered, line.time, WORD_PAIR_TOLERANCE_MS)
            }
            if (candidate == null || normalizeText(candidate.text) != normalizeText(line.text)) continue
            val adopted = adoptWords(candidate.words, line.text)
            if (adopted.isEmpty()) continue
            line.words = adopted.toMutableList()
            line.wordSource = "api"
            line.time = candidate.time
            matched += 1
        }
        if (matched > 0) {
            lines.sortBy { it.time }
            rebuildTimes()
        }
        return matched
    }

    fun applyPseudo(
        perCharMs: Double = PSEUDO_PER_CHAR_MS,
        minSpanMs: Int = PSEUDO_MIN_SPAN_MS,
        maxSpanMs: Double = PSEUDO_MAX_SPAN_MS
    ): Int {
        var made = 0
        val totalLines = lines.size
        for (index in lines.indices) {
            val line = lines[index]
            if (line.words.isNotEmpty() || line.text.isBlank()) continue
            val start = line.time
            val gap = if (index + 1 < totalLines) lines[index + 1].time - start else DEFAULT_LINE_MS
            val weights = line.text.map { charWeight(it) }
            val total = weights.sum().takeIf { it > 0.0 } ?: 1.0
            val natural = max(minSpanMs.toDouble(), total * perCharMs)
            var span = min(if (gap > 0) gap.toDouble() else DEFAULT_LINE_MS.toDouble(), natural)
            span = min(span, maxSpanMs)
            span = max(1.0, span)
            val words = mutableListOf<LyricWord>()
            var acc = 0.0
            for (idx in line.text.indices) {
                val share = span * (weights[idx] / total)
                val wordStart = start + acc.roundToInt()
                val wordEnd = start + (acc + share).roundToInt()
                words.add(
                    LyricWord(
                        text = line.text[idx].toString(),
                        start = max(0, wordStart),
                        duration = max(0, wordEnd - wordStart),
                        charStart = idx,
                        charEnd = idx + 1
                    )
                )
                acc += share
            }
            line.words = words
            line.wordSource = "pseudo"
            made += 1
        }
        return made
    }

    fun indexAt(elapsedMs: Int): Int {
        if (lines.isEmpty()) return -1
        if (elapsedMs < lines[0].time) return -1
        val cached = cacheIndex
        if (cached in lines.indices && lines[cached].time <= elapsedMs) {
            val next = if (cached + 1 < lines.size) lines[cached + 1].time else null
            if (next == null || elapsedMs < next) return cached
        }
        val index = upperBound(times, elapsedMs) - 1
        if (index < 0) return -1
        cacheKey = elapsedMs
        cacheIndex = index
        return index
    }

    fun lineAt(elapsedMs: Int): LyricLine? {
        val index = indexAt(elapsedMs)
        return if (index >= 0) lines[index] else null
    }

    fun window(elapsedMs: Int, before: Int = 2, after: Int = 6): List<Pair<Int, LyricLine>> {
        val index = indexAt(elapsedMs)
        if (index < 0) {
            return lines.take(max(0, after)).mapIndexed { i, line -> i to line }
        }
        val lo = max(0, index - before)
        val hi = min(lines.size, index + after + 1)
        return (lo until hi).map { it to lines[it] }
    }

    fun charProgress(elapsedMs: Int): Double {
        val index = indexAt(elapsedMs)
        if (index < 0) return 0.0
        val line = lines[index]
        if (line.words.isEmpty()) return 0.0
        val t = elapsedMs
        for (word in line.words) {
            if (t < word.start) return word.charStart.toDouble()
            if (word.duration <= 0) {
                if (t == word.start) return word.charEnd.toDouble()
                continue
            }
            if (t < word.start + word.duration) {
                val fraction = (t - word.start).toDouble() / word.duration
                val span = word.charEnd - word.charStart
                return word.charStart + span * fraction.coerceIn(0.0, 1.0)
            }
        }
        return line.text.length.toDouble()
    }

    private fun merge(raw: String?, translation: Boolean) {
        if (raw.isNullOrBlank() || lines.isEmpty()) return
        val sub = Lyrics()
        sub.parse(raw)
        if (sub.lines.isEmpty()) return
        val shift = offsetMs - sub.offsetMs
        if (shift != 0) {
            for (line in sub.lines) line.time = max(0, line.time + shift)
        }
        val lookup = LinkedHashMap<Int, String>()
        for (line in sub.lines) lookup.putIfAbsent(line.time, line.text)
        val ordered = lookup.keys.sorted()
        for (line in lines) {
            var text = lookup[line.time]
            if (text == null) text = nearest(lookup, ordered, line.time, PAIR_TOLERANCE_MS)
            if (!text.isNullOrBlank()) {
                if (translation) line.translation = text else line.roma = text
            }
        }
    }

    private fun parseLine(raw: String): List<LyricLine> {
        val line = raw.trim()
        if (line.isEmpty()) return emptyList()
        parseYrcLine(line, offsetMs)?.let { return it }
        val matches = TIME_TAG_RE.findAll(line).toList()
        if (matches.isEmpty()) return emptyList()
        var stripped = line
        for (match in matches) stripped = stripped.replaceFirst(match.value, "")
        val text = WORD_TAG_RE.replace(stripped, "").trim()
        if (text.isEmpty()) return emptyList()
        val result = mutableListOf<LyricLine>()
        for (match in matches) {
            val minutes = match.groupValues[1].toIntOrNull() ?: continue
            val seconds = match.groupValues[2].toIntOrNull() ?: continue
            val msText = match.groupValues[3].ifBlank { "0" }.padEnd(3, '0').take(3)
            val milliseconds = msText.toIntOrNull() ?: 0
            val time = max(0, (minutes * 60 + seconds) * 1000 + milliseconds + offsetMs)
            result.add(LyricLine(text = text, time = time))
        }
        return result
    }

    private fun parseYrcLine(line: String, offset: Int): List<LyricLine>? {
        val head = YRC_HEAD_RE.find(line) ?: return null
        val lineStart = head.groupValues[1].toIntOrNull() ?: return null
        val textStart = head.range.last + 1
        if (textStart >= line.length) return null
        val body = line.substring(textStart)
        val matches = YRC_WORD_RE.findAll(body).toList()
        if (matches.isEmpty()) return null
        val words = mutableListOf<LyricWord>()
        var cursor = 0
        var textBuilder = StringBuilder()
        for (match in matches) {
            val prefix = body.substring(cursor, match.range.first)
            if (prefix.isNotEmpty()) textBuilder.append(prefix)
            val start = match.groupValues[1].toIntOrNull() ?: 0
            val duration = match.groupValues[2].toIntOrNull() ?: 0
            val text = body.substring(match.range.last + 1).takeWhile { it != '(' && it != '\n' }
            val charStart = textBuilder.length
            textBuilder.append(text)
            words.add(LyricWord(text, max(0, start + offset), duration, charStart, charStart + text.length))
            cursor = match.range.last + 1 + text.length
        }
        val text = textBuilder.toString().trim()
        if (text.isEmpty() || words.isEmpty()) return null
        return listOf(
            LyricLine(
                text = text,
                time = max(0, lineStart + offset),
                words = words,
                wordSource = "api"
            )
        )
    }

    private fun adoptWords(words: List<LyricWord>, targetText: String): List<LyricWord> {
        val result = mutableListOf<LyricWord>()
        var targetPos = 0
        for (word in words) {
            var local = 0
            while (targetPos < targetText.length && targetText[targetPos].isWhitespace()) targetPos += 1
            val start = targetPos
            while (local < word.text.length && targetPos < targetText.length) {
                val sourceChar = word.text[local]
                if (sourceChar.isWhitespace()) {
                    local += 1
                    continue
                }
                if (targetText[targetPos].isWhitespace()) {
                    targetPos += 1
                    continue
                }
                local += 1
                targetPos += 1
            }
            if (targetPos > start) {
                result.add(word.copy(charStart = start, charEnd = targetPos))
            }
        }
        return result
    }

    private fun rebuildTimes() {
        times = lines.map { it.time }.toMutableList()
        cacheKey = -10000
        cacheIndex = -1
    }

    private fun upperBound(values: List<Int>, target: Int): Int {
        var lo = 0
        var hi = values.size
        while (lo < hi) {
            val mid = (lo + hi) ushr 1
            if (values[mid] <= target) lo = mid + 1 else hi = mid
        }
        return lo
    }

    companion object {
        const val DEFAULT_LINE_MS = 5000
        const val PAIR_TOLERANCE_MS = 150
        const val WORD_PAIR_TOLERANCE_MS = 1500
        const val PSEUDO_PER_CHAR_MS = 220.0
        const val PSEUDO_MIN_SPAN_MS = 800
        const val PSEUDO_MAX_SPAN_MS = 8000.0

        private val TIME_TAG_RE = Regex("\\[(\\d{1,3}):(\\d{2})(?:[.:](\\d{1,3}))?\\]")
        private val META_TAG_RE = Regex("\\[(ti|ar|al|offset|by|kuwo|tool|length):\\s*(.*?)\\s*\\]", RegexOption.IGNORE_CASE)
        private val YRC_HEAD_RE = Regex("^\\[(\\d{1,9}),(\\d{1,9})\\]")
        private val YRC_WORD_RE = Regex("\\((\\d{1,9}),(\\d{1,9}),(-?\\d+)\\)")
        private val WORD_TAG_RE = Regex("<(-?\\d+),(-?\\d+)(?:,-?\\d+)?>")

        private fun normalizeText(text: String): String = text.filterNot { it.isWhitespace() }.lowercase()

        private fun charWeight(ch: Char): Double {
            if (ch.isWhitespace()) return 0.15
            if (ch.isLetterOrDigit()) return if (ch.code > 0x2E80) 1.0 else 0.5
            return 0.4
        }

        private fun <T> nearest(lookup: Map<Int, T>, sorted: List<Int>, target: Int, tolerance: Int): T? {
            val pos = sorted.binarySearch(target).let { if (it < 0) -it - 1 else it }
            var best: T? = null
            var bestDelta = tolerance + 1
            for (index in intArrayOf(pos - 1, pos)) {
                if (index in sorted.indices) {
                    val delta = abs(sorted[index] - target)
                    if (delta <= tolerance && delta < bestDelta) {
                        bestDelta = delta
                        best = lookup[sorted[index]]
                    }
                }
            }
            return best
        }
    }
}
