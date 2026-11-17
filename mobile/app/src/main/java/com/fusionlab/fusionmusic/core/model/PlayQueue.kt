package com.fusionlab.fusionmusic.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.util.Random

enum class PlayMode(val id: Int, val configName: String, val label: String) {
    ORDER(0, "sequential", "顺序播放"),
    LOOP_LIST(1, "loop_list", "列表循环"),
    LOOP_SINGLE(2, "loop_single", "单曲循环"),
    SHUFFLE(3, "shuffle", "随机播放");

    companion object {
        fun fromName(name: String, fallback: PlayMode = LOOP_LIST): PlayMode {
            val normalized = name.trim().lowercase()
            return when (normalized) {
                "sequential", "order" -> ORDER
                "loop_list", "list_loop" -> LOOP_LIST
                "loop_single", "single" -> LOOP_SINGLE
                "shuffle", "random" -> SHUFFLE
                else -> fallback
            }
        }

        fun fromId(value: Int): PlayMode = entries.firstOrNull { it.id == value } ?: LOOP_LIST
    }
}

@Serializable
data class QueueSnapshot(
    val mode: String = "loop_list",
    val index: Int = 0,
    val tracks: List<Track> = emptyList()
)

class PlayQueue(private val onChanged: (() -> Unit)? = null) {
    private val tracks = mutableListOf<Track>()
    private var currentIndex: Int = -1
    private var currentMode: PlayMode = PlayMode.LOOP_LIST
    private val shuffleOrder = mutableListOf<Int>()
    private var shufflePos: Int = -1
    private val history = mutableListOf<Int>()
    private val random = Random()

    var mode: PlayMode
        get() = currentMode
        set(value) {
            if (value == currentMode) return
            currentMode = value
            if (value == PlayMode.SHUFFLE) {
                rebuildShuffle(startAtCurrent = true)
            }
            notifyChanged()
        }

    val index: Int
        get() = currentIndex

    val size: Int
        get() = tracks.size

    val isEmpty: Boolean
        get() = tracks.isEmpty()

    fun tracks(): List<Track> = tracks.toList()

    fun current(): Track? = tracks.getOrNull(currentIndex)

    fun at(index: Int): Track? = tracks.getOrNull(index)

    fun setTracks(items: List<Track>, startIndex: Int = 0) {
        tracks.clear()
        tracks.addAll(items)
        history.clear()
        currentIndex = if (tracks.isEmpty()) -1 else startIndex.coerceIn(0, tracks.size - 1)
        rebuildShuffle(startAtCurrent = true)
        notifyChanged()
    }

    fun append(track: Track): Int {
        tracks.add(track)
        if (currentMode == PlayMode.SHUFFLE) {
            shuffleOrder.add(tracks.size - 1)
        }
        if (currentIndex < 0 && tracks.isNotEmpty()) currentIndex = 0
        notifyChanged()
        return tracks.size - 1
    }

    fun extend(items: List<Track>) {
        val start = tracks.size
        tracks.addAll(items)
        if (currentMode == PlayMode.SHUFFLE) {
            for (index in start until tracks.size) shuffleOrder.add(index)
        }
        if (currentIndex < 0 && tracks.isNotEmpty()) currentIndex = 0
        notifyChanged()
    }

    fun insert(index: Int, track: Track): Int {
        val target = index.coerceIn(0, tracks.size)
        tracks.add(target, track)
        for (i in shuffleOrder.indices) {
            if (shuffleOrder[i] >= target) shuffleOrder[i] = shuffleOrder[i] + 1
        }
        if (currentMode == PlayMode.SHUFFLE) {
            shuffleOrder.add(0, target)
        }
        if (currentIndex >= target) currentIndex += 1
        rebuildShuffleIfNeeded()
        notifyChanged()
        return target
    }

    fun insertNext(track: Track): Int {
        if (currentIndex < 0) return append(track)
        return insert(currentIndex + 1, track)
    }

    fun removeAt(index: Int): Track? {
        if (index !in tracks.indices) return null
        val removed = tracks.removeAt(index)
        val filtered = mutableListOf<Int>()
        for (value in shuffleOrder) {
            if (value == index) continue
            filtered.add(if (value > index) value - 1 else value)
        }
        shuffleOrder.clear()
        shuffleOrder.addAll(filtered)
        when {
            index < currentIndex -> currentIndex -= 1
            index == currentIndex -> currentIndex = currentIndex.coerceAtMost(tracks.size - 1)
        }
        val historyFiltered = mutableListOf<Int>()
        for (value in history) {
            if (value == index) continue
            historyFiltered.add(if (value > index) value - 1 else value)
        }
        history.clear()
        history.addAll(historyFiltered)
        rebuildShuffleIfNeeded()
        notifyChanged()
        return removed
    }

    fun move(src: Int, dst: Int): Boolean {
        if (src !in tracks.indices || dst !in tracks.indices || src == dst) return false
        val item = tracks.removeAt(src)
        tracks.add(dst, item)
        when {
            currentIndex == src -> currentIndex = dst
            src < currentIndex && currentIndex <= dst -> currentIndex -= 1
            dst <= currentIndex && currentIndex < src -> currentIndex += 1
        }
        rebuildShuffle(startAtCurrent = true)
        notifyChanged()
        return true
    }

    fun clear() {
        tracks.clear()
        shuffleOrder.clear()
        history.clear()
        currentIndex = -1
        notifyChanged()
    }

    fun setIndex(index: Int, recordHistory: Boolean = true): Boolean {
        if (index !in tracks.indices) return false
        if (currentIndex != index && currentIndex in tracks.indices && recordHistory) {
            history.add(currentIndex)
            if (history.size > 500) {
                repeat(100) { if (history.isNotEmpty()) history.removeAt(0) }
            }
        }
        currentIndex = index
        if (currentMode == PlayMode.SHUFFLE) {
            val position = shuffleOrder.indexOf(index)
            if (position >= 0) shufflePos = position
        }
        notifyChanged()
        return true
    }

    fun nextIndex(manual: Boolean = false, autoAdvance: Boolean = false): Int? {
        val n = tracks.size
        if (n == 0) return null
        if (n == 1) return if (manual || autoAdvance) 0 else null
        if (currentMode == PlayMode.LOOP_SINGLE && autoAdvance) {
            return if (currentIndex >= 0) currentIndex else 0
        }
        if (currentMode == PlayMode.SHUFFLE) {
            if (shuffleOrder.size != n) rebuildShuffle(startAtCurrent = true)
            if (shufflePos + 1 >= shuffleOrder.size) {
                val last = if (shufflePos >= 0) shuffleOrder[shufflePos] else -1
                rebuildShuffle()
                if (shuffleOrder.size > 1 && shuffleOrder[0] == last) {
                    shuffleOrder.add(shuffleOrder.removeAt(0))
                }
                shufflePos = -1
            }
            shufflePos += 1
            return shuffleOrder[shufflePos]
        }
        val current = if (currentIndex >= 0) currentIndex else 0
        var next = current + 1
        if (next >= n) {
            if (currentMode == PlayMode.ORDER && autoAdvance) return null
            next = 0
        }
        return next
    }

    fun prevIndex(manual: Boolean = true): Int? {
        val n = tracks.size
        if (n == 0) return null
        if (n == 1) return 0
        if (manual && history.isNotEmpty()) {
            while (history.isNotEmpty()) {
                val value = history.removeAt(history.size - 1)
                if (value in tracks.indices && value != currentIndex) return value
            }
        }
        if (currentMode == PlayMode.SHUFFLE) {
            if (shufflePos > 0) {
                shufflePos -= 1
                return shuffleOrder[shufflePos]
            }
            return shuffleOrder.lastOrNull() ?: 0
        }
        val current = if (currentIndex >= 0) currentIndex else 0
        return (current - 1 + n) % n
    }

    fun toSnapshot(): QueueSnapshot = QueueSnapshot(
        mode = currentMode.configName,
        index = currentIndex,
        tracks = tracks.toList()
    )

    fun loadSnapshot(snapshot: QueueSnapshot?) {
        if (snapshot == null) return
        currentMode = PlayMode.fromName(snapshot.mode)
        setTracks(snapshot.tracks, snapshot.index.coerceAtLeast(0))
    }

    private fun rebuildShuffle(startAtCurrent: Boolean = false) {
        shuffleOrder.clear()
        for (i in tracks.indices) shuffleOrder.add(i)
        shuffleOrder.shuffle(random)
        if (startAtCurrent && currentIndex in tracks.indices) {
            val position = shuffleOrder.indexOf(currentIndex)
            if (position >= 0) {
                val value = shuffleOrder.removeAt(position)
                shuffleOrder.add(0, value)
            }
        }
        shufflePos = if (shuffleOrder.isEmpty()) -1 else 0
    }

    private fun rebuildShuffleIfNeeded() {
        if (currentMode == PlayMode.SHUFFLE && shuffleOrder.size != tracks.size) {
            rebuildShuffle(startAtCurrent = true)
        }
    }

    private fun notifyChanged() {
        onChanged?.invoke()
    }
}
