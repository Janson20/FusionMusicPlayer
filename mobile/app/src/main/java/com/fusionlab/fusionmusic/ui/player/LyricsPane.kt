package com.fusionlab.fusionmusic.ui.player

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fusionlab.fusionmusic.data.lyrics.LyricLine
import com.fusionlab.fusionmusic.data.lyrics.Lyrics

@Composable
fun LyricsPane(
    lyrics: Lyrics,
    positionMs: Long,
    baseFontSize: TextUnit,
    alignment: String,
    modifier: Modifier = Modifier
) {
    if (lyrics.isEmpty) {
        Text(
            text = "暂无歌词",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = modifier.padding(top = 24.dp),
            textAlign = TextAlign.Center
        )
        return
    }
    val listState = rememberLazyListState()
    val index = lyrics.indexAt(positionMs.toInt())
    val progress = lyrics.charProgress(positionMs.toInt())
    LaunchedEffect(index) {
        if (index >= 0) {
            listState.animateScrollToItem((index - 2).coerceAtLeast(0))
        }
    }
    LazyColumn(state = listState, modifier = modifier) {
        itemsIndexed(lyrics.lines) { lineIndex, line ->
            val current = lineIndex == index
            LyricLineView(
                line = line,
                current = current,
                progress = if (current) progress else -1.0,
                primary = MaterialTheme.colorScheme.primary,
                idle = MaterialTheme.colorScheme.onSurfaceVariant,
                baseFontSize = baseFontSize,
                alignment = alignment
            )
        }
    }
}

@Composable
private fun LyricLineView(
    line: LyricLine,
    current: Boolean,
    progress: Double,
    primary: Color,
    idle: Color,
    baseFontSize: TextUnit,
    alignment: String
) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Text(
            text = lyricText(line, if (current) progress else -1.0, primary, idle),
            fontSize = if (current) (baseFontSize.value + 2f).sp else (baseFontSize.value - 2f).sp,
            fontWeight = if (current) FontWeight.SemiBold else FontWeight.Normal,
            textAlign = when (alignment) {
                "left" -> TextAlign.Left
                "right" -> TextAlign.Right
                else -> TextAlign.Center
            },
            modifier = Modifier.fillMaxWidth()
        )
        if (line.hasSub) {
            Text(
                text = line.subText,
                fontSize = 12.sp,
                color = idle,
                textAlign = when (alignment) {
                    "left" -> TextAlign.Left
                    "right" -> TextAlign.Right
                    else -> TextAlign.Center
                },
                modifier = Modifier.fillMaxWidth().padding(top = 2.dp)
            )
        }
    }
}

private fun lyricText(line: LyricLine, progress: Double, primary: Color, idle: Color): AnnotatedString {
    if (progress < 0.0) return AnnotatedString(line.text)
    val builder = buildAnnotatedString {
        for (index in line.text.indices) {
            val color = when {
                (index + 1).toDouble() <= progress -> primary
                index.toDouble() < progress -> {
                    val fraction = (progress - index).toFloat().coerceIn(0f, 1f)
                    lerp(idle, primary, fraction)
                }
                else -> idle
            }
            withStyle(SpanStyle(color = color)) {
                append(line.text[index])
            }
        }
    }
    return builder
}
