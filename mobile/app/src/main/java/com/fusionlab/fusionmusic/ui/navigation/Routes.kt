package com.fusionlab.fusionmusic.ui.navigation

import android.net.Uri
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Download
import androidx.compose.material.icons.outlined.Explore
import androidx.compose.material.icons.outlined.LibraryMusic
import androidx.compose.material.icons.outlined.Radio
import androidx.compose.material.icons.outlined.Search
import androidx.compose.ui.graphics.vector.ImageVector
import com.fusionlab.fusionmusic.R

enum class TopDestination(
    val route: String,
    val labelRes: Int,
    val icon: ImageVector
) {
    DISCOVER("discover", R.string.nav_discover, Icons.Outlined.Explore),
    ROAM("roam", R.string.nav_roam, Icons.Outlined.Radio),
    SEARCH("search", R.string.nav_search, Icons.Outlined.Search),
    LIBRARY("library", R.string.nav_library, Icons.Outlined.LibraryMusic),
    DOWNLOADS("downloads", R.string.nav_downloads, Icons.Outlined.Download)
}

object Routes {
    const val NOW_PLAYING = "now_playing"
    const val QUEUE = "queue"
    const val SETTINGS = "settings"
    const val LOGIN = "login"
    const val DESKTOP_SCAN = "desktop_scan"
    const val LOCAL = "local"
    const val PLAYLIST_DETAIL = "playlist/{playlistId}"
    const val ARTIST_DETAIL = "artist/{artistId}?name={name}"
    const val ALBUM_DETAIL = "album/{albumId}?name={name}&artist={artist}"
    const val WIKI = "wiki"

    fun playlist(playlistId: String): String = "playlist/" + Uri.encode(playlistId)

    fun artist(artistId: String, name: String): String {
        return "artist/" + Uri.encode(artistId.ifBlank { EMPTY_ID }) + "?name=" + Uri.encode(name)
    }

    fun album(albumId: String, name: String, artist: String): String {
        return "album/" + Uri.encode(albumId.ifBlank { EMPTY_ID }) +
            "?name=" + Uri.encode(name) + "&artist=" + Uri.encode(artist)
    }

    const val EMPTY_ID = "_"
}
