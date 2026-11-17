package com.fusionlab.fusionmusic

import android.content.Context
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import com.fusionlab.fusionmusic.data.source.SourceRegistry
import com.fusionlab.fusionmusic.data.store.LibraryStore
import com.fusionlab.fusionmusic.data.store.SessionStore
import com.fusionlab.fusionmusic.playback.LoudnessService
import com.fusionlab.fusionmusic.playback.LyricsLoader
import com.fusionlab.fusionmusic.playback.MediaCache
import com.fusionlab.fusionmusic.playback.PlaybackRepository
import com.fusionlab.fusionmusic.playback.TrackResolver
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

class AppContainer(context: Context) {
    val appContext: Context = context.applicationContext
    val appScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    val log: AppLog = AppLog(appContext)
    val config: ConfigRepository = ConfigRepository(appContext, appScope)
    val library: LibraryStore = LibraryStore(appContext)
    val sessionStore: SessionStore = SessionStore(appContext)
    val playbackRepository: PlaybackRepository = PlaybackRepository(
        config = config,
        library = library,
        sessionStore = sessionStore,
        scope = appScope
    )
    val sourceRegistry: SourceRegistry by lazy { SourceRegistry(config, log) }
    val neteaseCatalog: com.fusionlab.fusionmusic.data.source.NeteaseCatalog by lazy {
        com.fusionlab.fusionmusic.data.source.NeteaseCatalog {
            sourceRegistry.getSource("wy") as? com.fusionlab.fusionmusic.data.source.NeteaseSource
        }
    }
    val account: com.fusionlab.fusionmusic.data.account.AccountRepository =
        com.fusionlab.fusionmusic.data.account.AccountRepository(
            context = appContext,
            config = config,
            sources = sourceRegistry,
            log = log,
            scope = appScope
        )
    val downloadRepository: com.fusionlab.fusionmusic.data.download.DownloadRepository =
        com.fusionlab.fusionmusic.data.download.DownloadRepository(appContext)
    val localRepository: com.fusionlab.fusionmusic.data.local.LocalRepository by lazy {
        com.fusionlab.fusionmusic.data.local.LocalRepository(
            context = appContext,
            config = config,
            library = library,
            sources = sourceRegistry,
            log = log,
            scope = appScope
        )
    }
    val mediaCache: MediaCache by lazy { MediaCache(appContext, log) }
    val artworkCache: com.fusionlab.fusionmusic.playback.ArtworkCache by lazy {
        com.fusionlab.fusionmusic.playback.ArtworkCache(appContext, log)
    }
    val trackResolver: TrackResolver by lazy {
        TrackResolver(appContext, config, sourceRegistry, mediaCache, log)
    }
    val lyricsLoader: LyricsLoader by lazy { LyricsLoader(appContext, config, sourceRegistry, log) }
    val loudnessService: LoudnessService by lazy {
        LoudnessService(appContext, config, sourceRegistry, log, appScope)
    }
    val updateRepository: com.fusionlab.fusionmusic.data.update.UpdateRepository by lazy {
        com.fusionlab.fusionmusic.data.update.UpdateRepository(appContext, config, log, appScope)
    }

    fun shutdown() {
        log.i("AppContainer", "shutting down")
        playbackRepository.saveSession()
        appScope.cancel()
    }
}
