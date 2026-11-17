package com.fusionlab.fusionmusic.data.download

import android.content.Context
import android.content.Intent
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.util.JsonFiles
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.File
import java.util.UUID

class DownloadRepository(context: Context) {
    private val appContext = context.applicationContext
    private val dataDir = File(context.filesDir, "data").apply { mkdirs() }
    private val file = File(dataDir, "downloads.json")
    private val lock = Any()
    private val state = MutableStateFlow<List<DownloadTask>>(emptyList())
    private val pending = MutableStateFlow<Track?>(null)

    val tasks: StateFlow<List<DownloadTask>> = state
    val pendingTrack: StateFlow<Track?> = pending

    init {
        val loaded = JsonFiles.read(file, emptyList<DownloadTask>(), JsonFiles.pretty)
        val recovered = loaded.map {
            if (it.status == DownloadTask.STATUS_RUNNING) {
                it.copy(
                    status = DownloadTask.STATUS_QUEUED,
                    progress = 0L,
                    speed = 0L,
                    error = "上次下载被中断，已重新排队",
                    updatedAt = System.currentTimeMillis()
                )
            } else {
                it
            }
        }
        state.value = recovered
        if (recovered != loaded) saveLocked(recovered)
    }

    fun requestDownload(track: Track) {
        pending.value = track
    }

    fun clearRequest() {
        pending.value = null
    }

    fun enqueue(tracks: List<Track>, quality: String): List<DownloadTask> {
        val created = mutableListOf<DownloadTask>()
        synchronized(lock) {
            val current = state.value.toMutableList()
            for (track in tracks) {
                if (track.isLocal) continue
                val task = DownloadTask(
                    id = "dl_" + UUID.randomUUID().toString().replace("-", "").take(12),
                    track = track,
                    quality = quality,
                    status = DownloadTask.STATUS_QUEUED,
                    createdAt = System.currentTimeMillis(),
                    updatedAt = System.currentTimeMillis()
                )
                current.add(0, task)
                created.add(task)
            }
            state.value = current
            saveLocked(current)
        }
        if (created.isNotEmpty()) startService() else return created
        return created
    }

    fun cancel(id: String) {
        update(id) { it.copy(status = DownloadTask.STATUS_CANCELED, updatedAt = System.currentTimeMillis()) }
        startService()
    }

    fun retry(id: String) {
        update(id) {
            it.copy(
                status = DownloadTask.STATUS_QUEUED,
                progress = 0L,
                total = 0L,
                speed = 0L,
                error = "",
                warning = "",
                updatedAt = System.currentTimeMillis()
            )
        }
        startService()
    }

    fun remove(id: String) {
        synchronized(lock) {
            val current = state.value.filterNot { it.id == id }
            state.value = current
            saveLocked(current)
        }
    }

    fun clearFinished() {
        synchronized(lock) {
            val current = state.value.filter { it.status == DownloadTask.STATUS_QUEUED || it.status == DownloadTask.STATUS_RUNNING }
            state.value = current
            saveLocked(current)
        }
    }

    fun markRunning(id: String) = update(id) {
        it.copy(
            status = DownloadTask.STATUS_RUNNING,
            error = "",
            warning = "",
            updatedAt = System.currentTimeMillis()
        )
    }

    fun updateProgress(id: String, progress: Long, total: Long, speed: Long = 0L) = update(id) {
        it.copy(progress = progress, total = total, speed = speed, updatedAt = System.currentTimeMillis())
    }

    fun markDone(
        id: String,
        targetPath: String,
        actualQuality: String,
        warning: String = ""
    ) = update(id) {
        it.copy(
            status = DownloadTask.STATUS_DONE,
            progress = if (it.total > 0) it.total else it.progress,
            speed = 0L,
            targetPath = targetPath,
            actualQuality = actualQuality,
            warning = warning,
            error = "",
            updatedAt = System.currentTimeMillis()
        )
    }

    fun markSkipped(id: String, message: String) = update(id) {
        it.copy(
            status = DownloadTask.STATUS_DONE,
            speed = 0L,
            error = message,
            updatedAt = System.currentTimeMillis()
        )
    }

    fun markFailed(id: String, message: String) = update(id) {
        it.copy(
            status = DownloadTask.STATUS_FAILED,
            error = message,
            speed = 0L,
            updatedAt = System.currentTimeMillis()
        )
    }

    fun nextQueued(limit: Int): List<DownloadTask> = synchronized(lock) {
        state.value.filter { it.status == DownloadTask.STATUS_QUEUED }.take(limit)
    }

    fun hasQueued(): Boolean = synchronized(lock) { state.value.any { it.status == DownloadTask.STATUS_QUEUED } }

    fun startService() {
        val intent = Intent(appContext, DownloadService::class.java).setAction(DownloadService.ACTION_START)
        appContext.startService(intent)
    }

    private fun update(id: String, block: (DownloadTask) -> DownloadTask) {
        synchronized(lock) {
            val current = state.value.toMutableList()
            val index = current.indexOfFirst { it.id == id }
            if (index < 0) return
            current[index] = block(current[index])
            state.value = current
            saveLocked(current)
        }
    }

    private fun saveLocked(tasks: List<DownloadTask>) {
        try {
            JsonFiles.writeAtomic(file, tasks, JsonFiles.pretty)
        } catch (_: Exception) {
            // Download state persistence is best effort.
        }
    }

    fun taskById(id: String): DownloadTask? = state.value.firstOrNull { it.id == id }
}
