package com.fusionlab.fusionmusic.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.R
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.account.DesktopScanScreen
import com.fusionlab.fusionmusic.ui.account.LoginScreen
import com.fusionlab.fusionmusic.ui.album.AlbumScreen
import com.fusionlab.fusionmusic.ui.artist.ArtistScreen
import com.fusionlab.fusionmusic.ui.components.AppBackground
import com.fusionlab.fusionmusic.ui.components.MiniPlayer
import com.fusionlab.fusionmusic.ui.discover.DiscoverScreen
import com.fusionlab.fusionmusic.ui.discover.PlaylistDetailScreen
import com.fusionlab.fusionmusic.ui.download.DownloadOptionsDialog
import com.fusionlab.fusionmusic.ui.download.DownloadsScreen
import com.fusionlab.fusionmusic.ui.library.LibraryScreen
import com.fusionlab.fusionmusic.ui.local.LocalScreen
import com.fusionlab.fusionmusic.ui.navigation.CatalogNavigator
import com.fusionlab.fusionmusic.ui.navigation.LocalCatalogNavigator
import com.fusionlab.fusionmusic.ui.navigation.LocalPlayerNavigator
import com.fusionlab.fusionmusic.ui.navigation.PlayerNavigator
import com.fusionlab.fusionmusic.ui.navigation.Routes
import com.fusionlab.fusionmusic.ui.navigation.TopDestination
import com.fusionlab.fusionmusic.ui.player.NowPlayingScreen
import com.fusionlab.fusionmusic.ui.player.QueueScreen
import com.fusionlab.fusionmusic.ui.roam.RoamScreen
import com.fusionlab.fusionmusic.ui.search.SearchScreen
import com.fusionlab.fusionmusic.ui.settings.SettingsScreen

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(container: AppContainer) {
    val navController = rememberNavController()
    val backStack by navController.currentBackStackEntryAsState()
    val route = backStack?.destination?.route ?: TopDestination.DISCOVER.route
    val topLevel = TopDestination.entries.firstOrNull { it.route == route }
    val snapshot by container.playbackRepository.snapshot.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val snackbar = remember { SnackbarHostState() }
    val pendingDownload by container.downloadRepository.pendingTrack.collectAsStateWithLifecycle()
    val configRevision by container.config.revisions.collectAsStateWithLifecycle()
    val backgroundImage = remember(configRevision) {
        if (container.config.getString("appearance.background", "solid") == "image") {
            container.config.getString("appearance.background_image", "")
        } else {
            ""
        }
    }
    val backgroundOpacity = remember(configRevision) { container.config.getInt("appearance.background_opacity", 85) }
    val backgroundBlur = remember(configRevision) { container.config.getInt("appearance.background_blur", 10) }
    val backgroundScrim = remember(configRevision) { container.config.getInt("appearance.background_scrim", 30) }
    val surfaceTop = remember(configRevision) {
        (container.config.getInt("appearance.surface_overlay", 35) / 100f).coerceIn(0.2f, 1f)
    }
    val surfaceBottom = remember(configRevision) {
        (container.config.getInt("appearance.surface_bottom", 40) / 100f).coerceIn(0.2f, 1f)
    }

    LaunchedEffect(snapshot.error) {
        val message = snapshot.error
        if (message != null) {
            snackbar.showSnackbar(message)
            container.playbackRepository.setError(null)
        }
    }

    if (pendingDownload != null) {
        DownloadOptionsDialog(
            track = pendingDownload ?: return,
            defaultQuality = container.config.getString("download.quality", "320k"),
            onDismiss = { container.downloadRepository.clearRequest() },
            onConfirm = { quality ->
                val track = pendingDownload
                if (track != null) {
                    container.downloadRepository.enqueue(listOf(track), quality)
                }
                container.downloadRepository.clearRequest()
            }
        )
    }

    Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
    AppBackground(
        imagePath = backgroundImage,
        opacity = backgroundOpacity,
        blurRadius = backgroundBlur,
        scrim = backgroundScrim
    )
    BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
    val wide = maxWidth >= 720.dp
    Row(modifier = Modifier.fillMaxSize()) {
    if (wide && topLevel != null) {
        NavigationRail(
            containerColor = MaterialTheme.colorScheme.surface.copy(alpha = surfaceTop),
            contentColor = MaterialTheme.colorScheme.onSurface
        ) {
            TopDestination.entries.forEach { destination ->
                NavigationRailItem(
                    selected = route == destination.route,
                    onClick = {
                        navController.navigate(destination.route) {
                            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    icon = { Icon(destination.icon, contentDescription = stringResource(destination.labelRes)) },
                    label = { Text(stringResource(destination.labelRes)) }
                )
            }
        }
    }
    Scaffold(
        modifier = if (wide) Modifier.weight(1f) else Modifier.fillMaxSize(),
        containerColor = Color.Transparent,
        contentColor = MaterialTheme.colorScheme.onBackground,
        topBar = {
            if (topLevel != null) {
                TopAppBar(
                    title = { Text(stringResource(topLevel.labelRes)) },
                    actions = {
                        IconButton(onClick = { navController.navigate(Routes.SETTINGS) }) {
                            Icon(Icons.Outlined.Settings, contentDescription = stringResource(R.string.settings))
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface.copy(alpha = surfaceTop),
                        titleContentColor = MaterialTheme.colorScheme.onSurface,
                        navigationIconContentColor = MaterialTheme.colorScheme.onSurface,
                        actionIconContentColor = MaterialTheme.colorScheme.onSurface
                    )
                )
            }
        },
        bottomBar = {
            if (topLevel != null) {
                Column {
                    MiniPlayer(
                        snapshot = snapshot,
                        onOpen = { navController.navigate(Routes.NOW_PLAYING) },
                        onToggle = { PlaybackController.toggle(context) },
                        onNext = { PlaybackController.next(context) }
                    )
                    if (!wide) NavigationBar(
                        containerColor = MaterialTheme.colorScheme.surface.copy(alpha = surfaceBottom),
                        contentColor = MaterialTheme.colorScheme.onSurface
                    ) {
                        TopDestination.entries.forEach { destination ->
                            NavigationBarItem(
                                selected = route == destination.route,
                                onClick = {
                                    navController.navigate(destination.route) {
                                        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                },
                                icon = { Icon(destination.icon, contentDescription = stringResource(destination.labelRes)) },
                                label = { Text(stringResource(destination.labelRes)) }
                            )
                        }
                    }
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbar) }
    ) { innerPadding ->
        CompositionLocalProvider(
            LocalCatalogNavigator provides CatalogNavigator(
                openArtist = { id, name -> navController.navigate(Routes.artist(id, name)) },
                openAlbum = { id, name, artist -> navController.navigate(Routes.album(id, name, artist)) }
            ),
            LocalPlayerNavigator provides PlayerNavigator {
                when (route) {
                    Routes.NOW_PLAYING -> Unit
                    Routes.QUEUE -> {
                        navController.popBackStack()
                    }
                    else -> {
                        if (!navController.popBackStack(Routes.NOW_PLAYING, false)) {
                            navController.navigate(Routes.NOW_PLAYING) { launchSingleTop = true }
                        }
                    }
                }
            }
        ) {
        NavHost(
            navController = navController,
            startDestination = TopDestination.DISCOVER.route,
            modifier = Modifier.fillMaxSize().padding(innerPadding)
        ) {
            composable(TopDestination.DISCOVER.route) {
                DiscoverScreen(container) { playlistId ->
                    navController.navigate("playlist/" + playlistId)
                }
            }
            composable(TopDestination.ROAM.route) { RoamScreen(container) }
            composable(TopDestination.SEARCH.route) { SearchScreen(container) }
            composable(TopDestination.LIBRARY.route) { LibraryScreen(container) }
            composable(TopDestination.DOWNLOADS.route) { DownloadsScreen(container) }
            composable(Routes.LOCAL) { LocalScreen(container) }
            composable(Routes.NOW_PLAYING) {
                NowPlayingScreen(
                    container = container,
                    onBack = { navController.popBackStack() },
                    onQueue = { navController.navigate(Routes.QUEUE) }
                )
            }
            composable(Routes.QUEUE) {
                QueueScreen(container, onBack = { navController.popBackStack() })
            }
            composable(Routes.SETTINGS) {
                SettingsScreen(
                    container,
                    onBack = { navController.popBackStack() },
                    onLogin = { navController.navigate(Routes.LOGIN) },
                    onDesktopScan = { navController.navigate(Routes.DESKTOP_SCAN) }
                )
            }
            composable(Routes.LOGIN) {
                LoginScreen(
                    container,
                    onBack = { navController.popBackStack() },
                    onDesktopScan = { navController.navigate(Routes.DESKTOP_SCAN) }
                )
            }
            composable(Routes.DESKTOP_SCAN) {
                DesktopScanScreen(
                    container,
                    onBack = { navController.popBackStack() },
                    onLoggedIn = {
                        // 登录成功后连登录页一起退掉，回到设置/上一级而不是停在登录页
                        if (!navController.popBackStack(Routes.LOGIN, true)) {
                            navController.popBackStack()
                        }
                    }
                )
            }
            composable(
                route = Routes.PLAYLIST_DETAIL,
                arguments = listOf(navArgument("playlistId") { type = NavType.StringType })
            ) { entry ->
                val playlistId = entry.arguments?.getString("playlistId") ?: ""
                PlaylistDetailScreen(
                    container = container,
                    playlistId = playlistId,
                    onBack = { navController.popBackStack() }
                )
            }
            composable(
                route = Routes.ARTIST_DETAIL,
                arguments = listOf(
                    navArgument("artistId") { type = NavType.StringType },
                    navArgument("name") {
                        type = NavType.StringType
                        defaultValue = ""
                    }
                )
            ) { entry ->
                ArtistScreen(
                    container = container,
                    artistId = (entry.arguments?.getString("artistId") ?: "").takeUnless { it == Routes.EMPTY_ID } ?: "",
                    artistName = entry.arguments?.getString("name") ?: "",
                    onBack = { navController.popBackStack() }
                )
            }
            composable(
                route = Routes.ALBUM_DETAIL,
                arguments = listOf(
                    navArgument("albumId") { type = NavType.StringType },
                    navArgument("name") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("artist") {
                        type = NavType.StringType
                        defaultValue = ""
                    }
                )
            ) { entry ->
                AlbumScreen(
                    container = container,
                    albumId = (entry.arguments?.getString("albumId") ?: "").takeUnless { it == Routes.EMPTY_ID } ?: "",
                    albumName = entry.arguments?.getString("name") ?: "",
                    artistName = entry.arguments?.getString("artist") ?: "",
                    onBack = { navController.popBackStack() }
                )
            }
        }
        }
    }
    }
    }
    }
}
