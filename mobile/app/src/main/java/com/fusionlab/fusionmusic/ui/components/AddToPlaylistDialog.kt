package com.fusionlab.fusionmusic.ui.components

import android.widget.Toast
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.Track

@Composable
fun AddToPlaylistDialog(
    container: AppContainer,
    tracks: List<Track>,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    val playlists = remember(tracks) { container.library.userPlaylists() }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("加入歌单（" + tracks.size + " 首）") },
        text = {
            if (playlists.isEmpty()) {
                Text("还没有自建歌单，请先在「我的」里创建。", style = MaterialTheme.typography.bodySmall)
            } else {
                Column(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 320.dp).verticalScroll(rememberScrollState())
                ) {
                    for (playlist in playlists) {
                        TextButton(
                            onClick = {
                                var added = 0
                                for (track in tracks) {
                                    if (container.library.addToPlaylist(playlist.id, track)) added++
                                }
                                Toast.makeText(context, "已加入 " + playlist.name + "（" + added + " 首）", Toast.LENGTH_SHORT).show()
                                onDismiss()
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(playlist.name + " · " + playlist.count + " 首")
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } }
    )
}
