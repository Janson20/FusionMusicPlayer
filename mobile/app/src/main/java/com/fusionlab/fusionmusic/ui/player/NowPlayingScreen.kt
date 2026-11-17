package com.fusionlab.fusionmusic.ui.player

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.outlined.Pause
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material.icons.outlined.QueueMusic
import androidx.compose.material.icons.outlined.Repeat
import androidx.compose.material.icons.outlined.RepeatOne
import androidx.compose.material.icons.outlined.Shuffle
import androidx.compose.material.icons.outlined.SkipNext
import androidx.compose.material.icons.outlined.SkipPrevious
import androidx.compose.material.icons.outlined.VolumeOff
import androidx.compose.material.icons.outlined.VolumeUp
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.PlayMode
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.source.WikiRow
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.playback.PlaybackSnapshot
import com.fusionlab.fusionmusic.ui.navigation.CatalogNavigator
import com.fusionlab.fusionmusic.ui.navigation.LocalCatalogNavigator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private const val PAGE_COVER = "cover"
private const val PAGE_LYRICS = "lyrics"
private const val PAGE_WIKI = "wiki"

private data class PlayerTab(val page: String, val label: String)

private val PLAYER_TABS = listOf(
    PlayerTab(PAGE_COVER, "封面"),
    PlayerTab(PAGE_LYRICS, "歌词"),
    PlayerTab(PAGE_WIKI, "百科")
)

@Composable
fun NowPlayingScreen(
    container: AppContainer,
    onBack: () -> Unit,
    onQueue: () -> Unit
) {
    val snapshot by container.playbackRepository.snapshot.collectAsStateWithLifecycle()
    val track = snapshot.current
    val context = LocalContext.current
    val configRevision by container.config.revisions.collectAsStateWithLifecycle()
    val catalogNavigator = LocalCatalogNavigator.current
    val lyricFontSize = remember(configRevision) {
        container.config.getInt("lyrics.font_size", 17).coerceIn(12, 26).sp
    }
    val seekStepSeconds = remember(configRevision) {
        (container.config.getInt("playback.seek_step_ms", 5000) / 1000).coerceAtLeast(1)
    }
    val muted = remember(configRevision) { container.config.getBoolean("playback.muted", false) }
    val lyricAlignment = remember(configRevision) { container.config.getString("lyrics.alignment", "center") }
    var page by rememberSaveable { mutableStateOf(PAGE_COVER) }
    var dragging by remember { mutableStateOf(false) }
    var sliderValue by remember { mutableFloatStateOf(0f) }
    var wikiLoading by remember { mutableStateOf(false) }
    var wikiRows by remember { mutableStateOf<List<WikiRow>>(emptyList()) }
    var wikiError by remember { mutableStateOf("") }

    LaunchedEffect(page, track?.uid) {
        if (page != PAGE_WIKI || track == null) return@LaunchedEffect
        wikiLoading = true
        wikiRows = emptyList()
        wikiError = ""
        val catalog = container.neteaseCatalog
        val pageData = withContext(Dispatchers.IO) {
            try {
                catalog.songWiki(
                    songId = if (track.source == "wy") track.songmid else "",
                    name = track.name,
                    singer = track.singer,
                    albumName = track.album,
                    albumId = if (track.source == "wy") track.albumId else "",
                    interval = track.interval
                )
            } catch (_: Exception) {
                null
            }
        }
        wikiRows = pageData?.rows ?: emptyList()
        wikiError = if (wikiRows.isEmpty()) "网易云的曲库里没有这首歌的百科" else ""
        wikiLoading = false
    }

    LaunchedEffect(snapshot.positionMs, dragging) {
        if (!dragging) sliderValue = snapshot.positionMs.toFloat()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background.copy(alpha = 0.9f))
            .padding(horizontal = 16.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Outlined.ArrowBack, contentDescription = "返回")
            }
            Text("正在播放", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            IconButton(onClick = onQueue) {
                Icon(Icons.Outlined.QueueMusic, contentDescription = "播放队列")
            }
        }

        if (track == null) {
            Text(
                "还没有在播放的歌曲",
                modifier = Modifier.padding(24.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            return@Column
        }

        val selectedTab = PLAYER_TABS.indexOfFirst { it.page == page }.coerceAtLeast(0)
        TabRow(
            selectedTabIndex = selectedTab,
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            containerColor = Color.Transparent,
            contentColor = MaterialTheme.colorScheme.primary,
            divider = {}
        ) {
            PLAYER_TABS.forEach { tab ->
                Tab(
                    selected = page == tab.page,
                    onClick = { page = tab.page },
                    text = { Text(tab.label, style = MaterialTheme.typography.labelLarge) },
                    selectedContentColor = MaterialTheme.colorScheme.primary,
                    unselectedContentColor = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Box(modifier = Modifier.fillMaxWidth().weight(1f)) {
            when (page) {
                PAGE_COVER -> CoverPage(
                    track = track,
                    snapshot = snapshot,
                    catalogNavigator = catalogNavigator,
                    onOpenLyrics = { page = PAGE_LYRICS },
                    modifier = Modifier.fillMaxSize()
                )
                PAGE_LYRICS -> PlayerOverlay(onDismiss = { page = PAGE_COVER }) {
                    LyricsPane(
                        lyrics = snapshot.lyrics,
                        positionMs = snapshot.positionMs,
                        baseFontSize = lyricFontSize,
                        alignment = lyricAlignment,
                        modifier = Modifier.fillMaxSize().padding(vertical = 8.dp)
                    )
                }
                else -> PlayerOverlay(onDismiss = { page = PAGE_COVER }) {
                    WikiPane(
                        loading = wikiLoading,
                        rows = wikiRows,
                        error = wikiError,
                        modifier = Modifier.fillMaxSize().padding(vertical = 8.dp)
                    )
                }
            }
        }

        Slider(
            value = sliderValue,
            onValueChange = {
                dragging = true
                sliderValue = it
            },
            onValueChangeFinished = {
                PlaybackController.seek(context, sliderValue.toLong())
                dragging = false
            },
            valueRange = 0f..(snapshot.durationMs.coerceAtLeast(1L).toFloat()),
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp)
        )
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(formatMillis(sliderValue.toLong()), style = MaterialTheme.typography.labelSmall)
            Text(formatMillis(snapshot.durationMs), style = MaterialTheme.typography.labelSmall)
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center
        ) {
            TextButton(onClick = {
                PlaybackController.seek(context, (snapshot.positionMs - seekStepSeconds * 1000L).coerceAtLeast(0L))
            }) { Text("−" + seekStepSeconds + " 秒") }
            TextButton(onClick = {
                PlaybackController.seek(
                    context,
                    (snapshot.positionMs + seekStepSeconds * 1000L).coerceAtMost(snapshot.durationMs.coerceAtLeast(0L))
                )
            }) { Text("+" + seekStepSeconds + " 秒") }
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            IconButton(onClick = { container.playbackRepository.cycleMode() }) {
                Icon(
                    imageVector = when (snapshot.mode) {
                        PlayMode.SHUFFLE -> Icons.Outlined.Shuffle
                        PlayMode.LOOP_SINGLE -> Icons.Outlined.RepeatOne
                        PlayMode.LOOP_LIST -> Icons.Outlined.Repeat
                        else -> Icons.Outlined.Repeat
                    },
                    contentDescription = snapshot.mode.label
                )
            }
            IconButton(onClick = { PlaybackController.previous(context) }) {
                Icon(Icons.Outlined.SkipPrevious, contentDescription = "上一首")
            }
            IconButton(onClick = { PlaybackController.toggle(context) }, modifier = Modifier.size(56.dp)) {
                Icon(
                    imageVector = if (snapshot.playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,
                    contentDescription = if (snapshot.playing) "暂停" else "播放",
                    modifier = Modifier.size(40.dp)
                )
            }
            IconButton(onClick = { PlaybackController.next(context) }) {
                Icon(Icons.Outlined.SkipNext, contentDescription = "下一首")
            }
            IconButton(onClick = { container.playbackRepository.toggleFavorite() }) {
                Icon(
                    imageVector = if (snapshot.favorite) Icons.Filled.Favorite else Icons.Outlined.FavoriteBorder,
                    contentDescription = "收藏"
                )
            }
            IconButton(onClick = { PlaybackController.toggleMute(context) }) {
                Icon(
                    imageVector = if (muted) Icons.Outlined.VolumeOff else Icons.Outlined.VolumeUp,
                    contentDescription = if (muted) "取消静音" else "静音"
                )
            }
        }
    }
}

@Composable
private fun CoverPage(
    track: Track,
    snapshot: PlaybackSnapshot,
    catalogNavigator: CatalogNavigator?,
    onOpenLyrics: () -> Unit,
    modifier: Modifier = Modifier
) {
    val interaction = remember { MutableInteractionSource() }
    BoxWithConstraints(modifier = modifier) {
        val coverSize = minOf(maxWidth * 0.74f, maxHeight * 0.56f, 280.dp).coerceAtLeast(120.dp)
        Column(
            modifier = Modifier
                .fillMaxSize()
                .clickable(
                    interactionSource = interaction,
                    indication = null,
                    onClick = onOpenLyrics
                )
                .padding(vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            AsyncImage(
                model = track.cover.ifBlank { null },
                contentDescription = "封面，轻点查看歌词",
                contentScale = ContentScale.Crop,
                modifier = Modifier.size(coverSize).clip(RoundedCornerShape(18.dp))
            )
            Text(
                text = track.name,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.fillMaxWidth().padding(top = 18.dp),
                textAlign = TextAlign.Center
            )
            Text(
                text = track.singer,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp).then(
                    if (catalogNavigator != null) {
                        Modifier.clickable {
                            catalogNavigator.openArtist("", track.singer.substringBefore("、").trim())
                        }
                    } else {
                        Modifier
                    }
                ),
                textAlign = TextAlign.Center
            )
            if (track.album.isNotBlank()) {
                Text(
                    text = track.album,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.fillMaxWidth().then(
                        if (catalogNavigator != null) {
                            Modifier.clickable {
                                catalogNavigator.openAlbum(
                                    if (track.source == "wy") track.albumId else "",
                                    track.album,
                                    track.singer.substringBefore("、").trim()
                                )
                            }
                        } else {
                            Modifier
                        }
                    ),
                    textAlign = TextAlign.Center
                )
            }
            Text(
                text = track.sourceText + " · " + track.qualityShort +
                    if (snapshot.loudnessText.isNotBlank()) " · " + snapshot.loudnessText else "",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.fillMaxWidth().padding(top = 2.dp),
                textAlign = TextAlign.Center
            )
            Text(
                text = "轻点封面查看歌词",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 10.dp)
            )
        }
    }
}

@Composable
private fun PlayerOverlay(
    onDismiss: () -> Unit,
    content: @Composable () -> Unit
) {
    val interaction = remember { MutableInteractionSource() }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .clickable(
                interactionSource = interaction,
                indication = null,
                onClick = onDismiss
            )
    ) {
        content()
    }
}

@Composable
private fun WikiPane(
    loading: Boolean,
    rows: List<WikiRow>,
    error: String,
    modifier: Modifier = Modifier
) {
    when {
        loading -> Box(modifier = modifier, contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        rows.isNotEmpty() -> LazyColumn(modifier = modifier) {
            items(rows) { row ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 7.dp),
                    verticalAlignment = Alignment.Top
                ) {
                    Text(
                        row.label,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(end = 12.dp)
                    )
                    Text(
                        row.value,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
        else -> Text(
            text = error.ifBlank { "暂无百科资料" },
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = modifier.padding(top = 24.dp),
            textAlign = TextAlign.Center
        )
    }
}

private fun formatMillis(ms: Long): String {
    val total = (ms / 1000).coerceAtLeast(0)
    val minutes = total / 60
    val seconds = total % 60
    return minutes.toString() + ":" + seconds.toString().padStart(2, '0')
}
