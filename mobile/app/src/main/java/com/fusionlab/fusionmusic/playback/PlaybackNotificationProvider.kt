package com.fusionlab.fusionmusic.playback

import android.content.Context
import android.os.Bundle
import androidx.media3.session.CommandButton
import androidx.media3.session.DefaultMediaNotificationProvider
import androidx.media3.session.MediaNotification
import androidx.media3.session.MediaSession
import androidx.media3.session.SessionCommand
import com.fusionlab.fusionmusic.R
import com.google.common.collect.ImmutableList

/**
 * Media3 filters notification actions through the controller's available
 * commands. The player only holds one MediaItem because the queue is managed by
 * PlaybackRepository, so "next" can be dropped even though it is a custom
 * session command. Add both transport buttons after that filtering step.
 */
class PlaybackNotificationProvider(context: Context) : MediaNotification.Provider {
    private val delegate = DefaultMediaNotificationProvider.Builder(context)
        .setChannelId(PlaybackService.PLAYBACK_CHANNEL_ID)
        .setChannelName(R.string.notification_channel_playback)
        .build()
        .apply { setSmallIcon(R.drawable.ic_stat_fusion) }

    override fun createNotification(
        session: MediaSession,
        customLayout: ImmutableList<CommandButton>,
        actionFactory: MediaNotification.ActionFactory,
        callback: MediaNotification.Provider.Callback
    ): MediaNotification {
        return delegate.createNotification(
            session,
            ensureTransportButtons(customLayout),
            actionFactory,
            callback
        )
    }

    override fun handleCustomCommand(
        session: MediaSession,
        customAction: String,
        extras: Bundle
    ): Boolean = delegate.handleCustomCommand(session, customAction, extras)

    override fun getNotificationChannelInfo(): MediaNotification.Provider.NotificationChannelInfo =
        delegate.notificationChannelInfo

    private fun ensureTransportButtons(layout: ImmutableList<CommandButton>): ImmutableList<CommandButton> {
        val hasPrevious = layout.any { it.hasSlot(CommandButton.SLOT_BACK) }
        val hasNext = layout.any { it.hasSlot(CommandButton.SLOT_FORWARD) }
        if (hasPrevious && hasNext) return layout
        val builder = ImmutableList.builder<CommandButton>().addAll(layout)
        if (!hasPrevious) {
            builder.add(
                CommandButton.Builder(CommandButton.ICON_PREVIOUS)
                    .setDisplayName("上一首")
                    .setSessionCommand(
                        SessionCommand(PlaybackService.ACTION_NOTIFICATION_PREVIOUS, Bundle.EMPTY)
                    )
                    .setSlots(CommandButton.SLOT_BACK)
                    .build()
            )
        }
        if (!hasNext) {
            builder.add(
                CommandButton.Builder(CommandButton.ICON_NEXT)
                    .setDisplayName("下一首")
                    .setSessionCommand(
                        SessionCommand(PlaybackService.ACTION_NOTIFICATION_NEXT, Bundle.EMPTY)
                    )
                    .setSlots(CommandButton.SLOT_FORWARD)
                    .build()
            )
        }
        return builder.build()
    }

    private fun CommandButton.hasSlot(slot: Int): Boolean {
        if (!isEnabled) return false
        for (index in 0 until slots.length()) {
            if (slots.get(index) == slot) return true
        }
        return false
    }
}
