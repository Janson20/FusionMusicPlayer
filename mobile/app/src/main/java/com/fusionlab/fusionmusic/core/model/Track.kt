package com.fusionlab.fusionmusic.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.Transient
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive

@Serializable
data class Track(
    val source: String = "",
    val songmid: String = "",
    val name: String = "",
    val singer: String = "",
    val album: String = "",
    @SerialName("album_id") val albumId: String = "",
    val interval: Int = 0,
    var cover: String = "",
    val fee: Int = 0,
    @SerialName("publish_time") val publishTime: Long = 0L,
    @SerialName("is_original") val isOriginal: Boolean = false,
    @SerialName("original_name") val originalName: String = "",
    @SerialName("origin_song_id") val originSongId: String = "",
    @SerialName("origin_artists") val originArtists: List<String> = emptyList(),
    val types: List<JsonObject> = emptyList(),
    @SerialName("type_detail") val typeDetail: Map<String, JsonObject> = emptyMap(),
    @SerialName("play_count") val playCount: Long = 0L,
    val path: String = "",
    @SerialName("match_source") var matchSource: String = "",
    @SerialName("match_songmid") var matchSongmid: String = "",
    @SerialName("added_at") val addedAt: Long = 0L
) {
    @Transient
    var reason: String = ""

    val uid: String
        get() = source + ":" + songmid

    val isLocal: Boolean
        get() = source == LOCAL_SOURCE

    val durationText: String
        get() = formatDuration(interval)

    val sourceText: String
        get() = SourceRegistryMeta.display(source)

    val qualityList: List<String>
        get() = types.mapNotNull { item ->
            item["type"]?.jsonPrimitive?.content?.takeIf { it.isNotBlank() }
        }

    val bestQuality: String
        get() {
            for (quality in QualityLevel.ALL) {
                if (qualityList.contains(quality)) return quality
            }
            return QualityLevel.LOW
        }

    val qualityShort: String
        get() = qualityShort(bestQuality)

    val displayName: String
        get() = if (originalName.isNotBlank() && !name.contains(originalName)) {
            name + "（原唱：" + originalName + "）"
        } else {
            name
        }

    fun sameSong(other: Track): Boolean =
        source == other.source && songmid.isNotBlank() && songmid == other.songmid

    fun toMusicInfo(): MusicInfo = MusicInfo(
        name = name,
        singer = singer,
        source = source,
        songmid = songmid,
        albumName = album,
        albumId = albumId,
        interval = interval,
        img = cover.ifBlank { null },
        types = types,
        typeDetail = typeDetail,
        publishTime = publishTime,
        isOriginal = isOriginal,
        originSongId = originSongId,
        originArtists = originArtists,
        fee = fee,
        originalName = originalName,
        playCount = playCount
    )

    companion object {
        const val LOCAL_SOURCE = "local"

        fun fromMusicInfo(info: MusicInfo): Track = Track(
            source = info.source,
            songmid = info.songmid,
            name = info.name,
            singer = info.singer,
            album = info.albumName,
            albumId = info.albumId,
            interval = info.interval,
            cover = info.img ?: "",
            fee = info.fee,
            publishTime = info.publishTime,
            isOriginal = info.isOriginal,
            originalName = info.originalName,
            originSongId = info.originSongId,
            originArtists = info.originArtists,
            types = info.types,
            typeDetail = info.typeDetail,
            playCount = info.playCount
        )
    }
}
