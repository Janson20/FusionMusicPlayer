package com.fusionlab.fusionmusic.playback

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.ForwardingPlayer
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import android.os.Bundle
import androidx.media3.session.CommandButton
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionResult
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import com.fusionlab.fusionmusic.FusionApplication
import com.fusionlab.fusionmusic.MainActivity
import com.fusionlab.fusionmusic.R
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.lyrics.Lyrics
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@UnstableApi
class PlaybackService : MediaSessionService() {
    private lateinit var exoPlayer: ExoPlayer
    private lateinit var player: ForwardingPlayer
    private val loudnessProvider = LoudnessGainProvider()
    private lateinit var mediaSession: MediaSession
    private lateinit var container: com.fusionlab.fusionmusic.AppContainer
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var resolveJob: Job? = null
    private var tickerJob: Job? = null
    private var fadeJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        container = (application as FusionApplication).container
        getSystemService(NotificationManager::class.java)?.createNotificationChannel(
            NotificationChannel(
                PLAYBACK_CHANNEL_ID,
                getString(R.string.notification_channel_playback),
                NotificationManager.IMPORTANCE_LOW
            ).apply { setShowBadge(false) }
        )
        setMediaNotificationProvider(PlaybackNotificationProvider(this))
        // Keep play/pause controls visible while a track is resolving or paused.
        setShowNotificationForIdlePlayer(MediaSessionService.SHOW_NOTIFICATION_FOR_IDLE_PLAYER_ALWAYS)
        exoPlayer = ExoPlayer.Builder(
            this,
            FusionRenderersFactory(this, createLoudnessGainProcessor(loudnessProvider))
        ).build()
        exoPlayer.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                .build(),
            true
        )
        exoPlayer.setHandleAudioBecomingNoisy(true)
        exoPlayer.volume = if (container.config.getBoolean("playback.muted", false)) 0f else {
            container.config.getInt("playback.volume", 65).coerceIn(0, 100) / 100f
        }
        player = object : ForwardingPlayer(exoPlayer) {
            override fun getAvailableCommands(): Player.Commands =
                super.getAvailableCommands().buildUpon()
                    .add(Player.COMMAND_SEEK_TO_PREVIOUS)
                    .add(Player.COMMAND_SEEK_TO_NEXT)
                    .add(Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM)
                    .add(Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM)
                    .build()

            override fun isCommandAvailable(command: Int): Boolean {
                if (command == Player.COMMAND_SEEK_TO_PREVIOUS ||
                    command == Player.COMMAND_SEEK_TO_NEXT ||
                    command == Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM ||
                    command == Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM
                ) {
                    return true
                }
                return super.isCommandAvailable(command)
            }

            override fun seekToPrevious() = previous()

            override fun seekToPreviousMediaItem() = previous()

            override fun seekToNext() = next()

            override fun seekToNextMediaItem() = next()
        }

        val sessionActivity = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE
        )
        val nextCommand = SessionCommand(ACTION_NOTIFICATION_NEXT, Bundle.EMPTY)
        val previousCommand = SessionCommand(ACTION_NOTIFICATION_PREVIOUS, Bundle.EMPTY)
        val customLayout = listOf(
            CommandButton.Builder(CommandButton.ICON_PREVIOUS)
                .setDisplayName("上一首")
                .setSessionCommand(previousCommand)
                .setSlots(CommandButton.SLOT_BACK)
                .build(),
            CommandButton.Builder(CommandButton.ICON_NEXT)
                .setDisplayName("下一首")
                .setSessionCommand(nextCommand)
                .setSlots(CommandButton.SLOT_FORWARD)
                .build()
        )
        mediaSession = MediaSession.Builder(this, player)
            .setSessionActivity(sessionActivity)
            .setMediaButtonPreferences(customLayout)
            .setCallback(object : MediaSession.Callback {
                override fun onCustomCommand(
                    session: MediaSession,
                    controller: MediaSession.ControllerInfo,
                    customCommand: SessionCommand,
                    args: Bundle
                ): ListenableFuture<SessionResult> {
                    when (customCommand.customAction) {
                        ACTION_NOTIFICATION_NEXT -> {
                            next()
                            return Futures.immediateFuture(SessionResult(SessionResult.RESULT_SUCCESS))
                        }
                        ACTION_NOTIFICATION_PREVIOUS -> {
                            previous()
                            return Futures.immediateFuture(SessionResult(SessionResult.RESULT_SUCCESS))
                        }
                    }
                    return super.onCustomCommand(session, controller, customCommand, args)
                }
            })
            .build()
        // Media3 only registers a session when a controller connects. Adding it
        // eagerly keeps the media notification and lock-screen controls alive
        // even though this app uses the service directly.
        addSession(mediaSession)

        player.addListener(object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                container.playbackRepository.setPlaying(isPlaying)
            }

            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_READY) {
                    container.playbackRepository.setDuration(player.duration)
                }
                if (playbackState == Player.STATE_ENDED) {
                    advanceAuto()
                }
            }

            override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                container.log.e("PlaybackService", "player error: " + (error.message ?: "unknown"))
                container.playbackRepository.setLoading(false)
                container.playbackRepository.setError("播放失败，正在尝试下一首")
                advanceAuto()
            }
        })

        startTicker()
        serviceScope.launch {
            container.loudnessService.revisions.collect {
                applyLoudness(container.playbackRepository.snapshot.value.current)
            }
        }
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession = mediaSession

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_PLAY_INDEX -> {
                val index = intent.getIntExtra(EXTRA_INDEX, 0)
                playIndex(index)
            }
            ACTION_TOGGLE -> toggle()
            ACTION_PLAY -> resume()
            ACTION_PAUSE -> player.pause()
            ACTION_NEXT -> next()
            ACTION_PREVIOUS -> previous()
            ACTION_SEEK -> player.seekTo(intent.getLongExtra(EXTRA_POSITION, 0L))
            ACTION_SET_VOLUME -> {
                val volume = intent.getIntExtra(EXTRA_VOLUME, 65).coerceIn(0, 100)
                container.config.setInt("playback.volume", volume)
                container.config.setBoolean("playback.muted", false)
                fadeJob?.cancel()
                player.volume = volume / 100f
            }
            ACTION_TOGGLE_MUTE -> {
                val muted = !container.config.getBoolean("playback.muted", false)
                container.config.setBoolean("playback.muted", muted)
                fadeJob?.cancel()
                player.volume = if (muted) 0f else {
                    container.config.getInt("playback.volume", 65).coerceIn(0, 100) / 100f
                }
            }
            ACTION_STOP -> {
                player.stop()
                loudnessProvider.setGainDb(0.0)
                container.playbackRepository.setLoudnessText("")
                container.playbackRepository.setPlaying(false)
                container.playbackRepository.saveSession()
                stopSelf()
            }
        }
        return START_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        if (!player.isPlaying) {
            stopSelf()
        }
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        resolveJob?.cancel()
        tickerJob?.cancel()
        fadeJob?.cancel()
        container.playbackRepository.saveSession()
        mediaSession.release()
        player.release()
        serviceScope.cancel()
        super.onDestroy()
    }

    private fun playIndex(index: Int) {
        if (container.playbackRepository.playIndex(index)) {
            loadCurrent(recordHistory = true)
        }
    }

    private fun loadCurrent(recordHistory: Boolean = false) {
        val track = container.playbackRepository.currentTrack() ?: return
        if (recordHistory) container.playbackRepository.markHistory(track)
        resolveJob?.cancel()
        container.playbackRepository.setLoading(true)
        container.playbackRepository.setError(null)
        container.playbackRepository.setFallbackSource("")
        val quality = container.config.getString("playback.quality", "320k")
        val allowFallback = container.config.getBoolean("sources.fallback", true)
        val cacheMedia = container.config.getBoolean("storage.cache_media", false)
        resolveJob = serviceScope.launch {
            val resolved = try {
                container.trackResolver.resolve(track, quality, allowFallback, cacheMedia)
            } catch (error: Exception) {
                container.log.e("PlaybackService", "resolve failed", error)
                null
            }
            if (resolved == null) {
                container.playbackRepository.setLoading(false)
                container.playbackRepository.setError("无法播放「" + track.name + "」：所有音源均不可用")
                return@launch
            }
            container.playbackRepository.setCurrent(resolved.track, resolved.requested)
            container.playbackRepository.setQuality(resolved.quality)
            container.playbackRepository.setFallbackSource(if (resolved.fallback) resolved.track.source else "")
            container.playbackRepository.setError(null)
            applyLoudness(resolved.track)
            container.loudnessService.request(
                track = resolved.track,
                target = resolved.uri.toString(),
                local = resolved.isLocal,
                focus = true
            )
            prefetchNextLoudness()
            val metadata = MediaMetadata.Builder()
                .setTitle(resolved.track.name)
                .setArtist(resolved.track.singer)
                .setAlbumTitle(resolved.track.album)
                .apply {
                    val cover = resolved.track.cover
                    if (cover.isNotBlank()) {
                        setArtworkUri(container.artworkCache.cached(cover) ?: Uri.parse(cover))
                    }
                }
                .build()
            val item = MediaItem.Builder()
                .setUri(resolved.uri)
                .setMediaMetadata(metadata)
                .build()
            player.setMediaItem(item)
            player.prepare()
            val fadeMs = container.config.getInt("playback.fade_in_ms", 0).coerceIn(0, 3000)
            val targetVolume = if (container.config.getBoolean("playback.muted", false)) 0f else {
                container.config.getInt("playback.volume", 65).coerceIn(0, 100) / 100f
            }
            player.volume = if (fadeMs > 0) 0f else targetVolume
            player.play()
            if (fadeMs > 0) fadeIn(targetVolume, fadeMs)
            container.playbackRepository.setLoading(false)
            if (resolved.track.cover.isNotBlank() && container.artworkCache.cached(resolved.track.cover) == null) {
                serviceScope.launch {
                    container.artworkCache.ensure(resolved.track.cover)
                }
            }
            loadLyrics(resolved.track)
        }
    }

    private fun fadeIn(target: Float, durationMs: Int) {
        fadeJob?.cancel()
        fadeJob = serviceScope.launch {
            val steps = 20
            val stepMs = (durationMs / steps).coerceAtLeast(20)
            for (index in 1..steps) {
                if (!player.isPlaying && index < steps) break
                player.volume = target * (index.toFloat() / steps)
                delay(stepMs.toLong())
            }
            player.volume = target
        }
    }

    private fun applyLoudness(track: Track?) {
        val gain = container.loudnessService.gainFor(track)
        loudnessProvider.setGainDb(gain)
        container.playbackRepository.setLoudnessText(container.loudnessService.describe(track))
    }

    private fun prefetchNextLoudness() {
        if (!container.config.getBoolean("audio.equalize", true)) return
        if (!container.config.getBoolean("audio.prefetch_next", true)) return
        val repository = container.playbackRepository
        val mode = repository.queue.mode
        if (mode == com.fusionlab.fusionmusic.core.model.PlayMode.SHUFFLE ||
            mode == com.fusionlab.fusionmusic.core.model.PlayMode.LOOP_SINGLE
        ) return
        val index = repository.queue.index
        val tracks = repository.queue.tracks()
        if (index < 0 || tracks.size < 2) return
        val currentUid = repository.snapshot.value.current?.uid ?: return
        val next = tracks[(index + 1) % tracks.size]
        if (next.uid == currentUid) return
        val quality = container.config.getString("playback.quality", "320k")
        val allowFallback = container.config.getBoolean("sources.fallback", true)
        val cacheMedia = container.config.getBoolean("storage.cache_media", false)
        serviceScope.launch {
            delay(2500)
            if (repository.snapshot.value.current?.uid != currentUid) return@launch
            val resolved = try {
                container.trackResolver.resolve(next, quality, allowFallback, cacheMedia)
            } catch (_: Exception) {
                null
            } ?: return@launch
            if (repository.snapshot.value.current?.uid != currentUid) return@launch
            container.loudnessService.prefetch(
                track = resolved.track,
                target = resolved.uri.toString(),
                local = resolved.isLocal
            )
        }
    }

    private fun loadLyrics(track: Track) {
        serviceScope.launch {
            val lyrics = withContext(Dispatchers.IO) {
                try {
                    container.lyricsLoader.load(track)
                } catch (error: Exception) {
                    container.log.w("PlaybackService", "lyrics failed: " + error.message)
                    Lyrics()
                }
            }
            container.playbackRepository.setLyrics(lyrics)
        }
    }

    private fun toggle() {
        if (player.isPlaying) {
            player.pause()
        } else if (player.mediaItemCount > 0) {
            player.play()
        } else {
            resume()
        }
    }

    private fun resume() {
        if (player.mediaItemCount > 0) {
            player.play()
        } else {
            val index = container.playbackRepository.queue.index
            if (index >= 0) playIndex(index) else if (container.playbackRepository.queue.size > 0) playIndex(0)
        }
    }

    private fun next() {
        if (container.playbackRepository.applyNext(manual = true, autoAdvance = false)) {
            loadCurrent()
        }
    }

    private fun previous() {
        if (container.playbackRepository.applyPrevious()) {
            loadCurrent()
        }
    }

    private fun advanceAuto() {
        if (container.config.getBoolean("playback.auto_play_next", true) &&
            container.playbackRepository.applyNext(manual = false, autoAdvance = true)
        ) {
            loadCurrent()
        } else {
            container.playbackRepository.setPlaying(false)
        }
    }

    private fun startTicker() {
        tickerJob = serviceScope.launch {
            while (isActive) {
                if (player.mediaItemCount > 0) {
                    container.playbackRepository.setPosition(player.currentPosition)
                    container.playbackRepository.setDuration(player.duration)
                }
                delay(250)
            }
        }
    }

    companion object {
        const val ACTION_PLAY_INDEX = "com.fusionlab.fusionmusic.PLAY_INDEX"
        const val ACTION_TOGGLE = "com.fusionlab.fusionmusic.TOGGLE"
        const val ACTION_PLAY = "com.fusionlab.fusionmusic.PLAY"
        const val ACTION_PAUSE = "com.fusionlab.fusionmusic.PAUSE"
        const val ACTION_NEXT = "com.fusionlab.fusionmusic.NEXT"
        const val ACTION_PREVIOUS = "com.fusionlab.fusionmusic.PREVIOUS"
        const val ACTION_SEEK = "com.fusionlab.fusionmusic.SEEK"
        const val ACTION_SET_VOLUME = "com.fusionlab.fusionmusic.SET_VOLUME"
        const val ACTION_TOGGLE_MUTE = "com.fusionlab.fusionmusic.TOGGLE_MUTE"
        const val ACTION_STOP = "com.fusionlab.fusionmusic.STOP"
        const val EXTRA_INDEX = "index"
        const val EXTRA_POSITION = "position"
        const val EXTRA_VOLUME = "volume"
        const val ACTION_NOTIFICATION_NEXT = "com.fusionlab.fusionmusic.NOTIFICATION_NEXT"
        const val ACTION_NOTIFICATION_PREVIOUS = "com.fusionlab.fusionmusic.NOTIFICATION_PREVIOUS"
        const val PLAYBACK_CHANNEL_ID = "fusion_playback"
    }
}
