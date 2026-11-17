package com.fusionlab.fusionmusic.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Session(
    val version: Int = 1,
    @SerialName("saved_at") val savedAt: Long = 0L,
    @SerialName("position_ms") val positionMs: Long = 0L,
    val queue: QueueSnapshot = QueueSnapshot()
) {
    companion object {
        const val SCHEMA_VERSION = 1
    }
}
