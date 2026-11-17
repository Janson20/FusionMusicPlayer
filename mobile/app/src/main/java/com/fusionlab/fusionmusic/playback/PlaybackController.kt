package com.fusionlab.fusionmusic.playback

import android.content.Context
import android.content.Intent
import com.fusionlab.fusionmusic.FusionApplication
import com.fusionlab.fusionmusic.core.model.Track

object PlaybackController {
    fun playTracks(context: Context, tracks: List<Track>, index: Int) {
        container(context).playbackRepository.setTracks(tracks, index)
        val intent = Intent(context, PlaybackService::class.java)
            .setAction(PlaybackService.ACTION_PLAY_INDEX)
            .putExtra(PlaybackService.EXTRA_INDEX, index)
        context.startService(intent)
    }

    fun playIndex(context: Context, index: Int) {
        val intent = Intent(context, PlaybackService::class.java)
            .setAction(PlaybackService.ACTION_PLAY_INDEX)
            .putExtra(PlaybackService.EXTRA_INDEX, index)
        context.startService(intent)
    }

    fun toggle(context: Context) {
        send(context, PlaybackService.ACTION_TOGGLE)
    }

    fun next(context: Context) {
        send(context, PlaybackService.ACTION_NEXT)
    }

    fun previous(context: Context) {
        send(context, PlaybackService.ACTION_PREVIOUS)
    }

    fun seek(context: Context, positionMs: Long) {
        val intent = Intent(context, PlaybackService::class.java)
            .setAction(PlaybackService.ACTION_SEEK)
            .putExtra(PlaybackService.EXTRA_POSITION, positionMs)
        context.startService(intent)
    }

    fun setVolume(context: Context, volume: Int) {
        val intent = Intent(context, PlaybackService::class.java)
            .setAction(PlaybackService.ACTION_SET_VOLUME)
            .putExtra(PlaybackService.EXTRA_VOLUME, volume)
        context.startService(intent)
    }

    fun toggleMute(context: Context) {
        send(context, PlaybackService.ACTION_TOGGLE_MUTE)
    }

    fun stop(context: Context) {
        send(context, PlaybackService.ACTION_STOP)
    }

    private fun send(context: Context, action: String) {
        context.startService(Intent(context, PlaybackService::class.java).setAction(action))
    }

    private fun container(context: Context) =
        (context.applicationContext as FusionApplication).container
}
