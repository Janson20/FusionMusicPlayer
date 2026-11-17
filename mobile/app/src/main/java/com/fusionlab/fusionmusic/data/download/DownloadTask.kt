package com.fusionlab.fusionmusic.data.download

import com.fusionlab.fusionmusic.core.model.Track
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class DownloadTask(
    val id: String,
    val track: Track,
    val quality: String = "320k",
    val status: String = STATUS_QUEUED,
    val progress: Long = 0L,
    val total: Long = 0L,
    val speed: Long = 0L,
    val error: String = "",
    @SerialName("actual_quality") val actualQuality: String = "",
    @SerialName("target_path") val targetPath: String = "",
    @SerialName("warning") val warning: String = "",
    @SerialName("created_at") val createdAt: Long = 0L,
    @SerialName("updated_at") val updatedAt: Long = 0L
) {
    val running: Boolean get() = status == STATUS_RUNNING || status == STATUS_QUEUED

    companion object {
        const val STATUS_QUEUED = "queued"
        const val STATUS_RUNNING = "running"
        const val STATUS_DONE = "done"
        const val STATUS_FAILED = "failed"
        const val STATUS_CANCELED = "canceled"
    }
}
