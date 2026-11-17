package com.fusionlab.fusionmusic.playback

import android.content.Context
import androidx.media3.common.audio.AudioProcessor
import androidx.media3.common.audio.GainProcessor
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.audio.AudioSink
import androidx.media3.exoplayer.audio.DefaultAudioSink
import com.fusionlab.fusionmusic.core.loudness.LoudnessGain
import kotlin.math.abs

/**
 * 把音量均衡的线性增益插进 ExoPlayer 的音频处理器链。
 *
 * 用 GainProcessor 而不是 player.volume：后者只适合 0..1 的衰减，
 * 而均衡既可能衰减也可能抬升（最多 +12 dB），还会和用户音量互相干扰。
 * 处理器链只作用于解码后的 PCM，不改变播放器音量与媒体会话。
 */
@UnstableApi
class LoudnessGainProvider : GainProcessor.GainProvider {
    @Volatile
    var factor: Float = 1.0f
        private set

    fun setGainDb(db: Double) {
        factor = LoudnessGain.dbToRatio(db).toFloat().coerceIn(0.0f, 8.0f)
    }

    override fun getGainFactorAtSamplePosition(samplePosition: Long, sampleCount: Int): Float = factor

    override fun isUnityUntil(samplePosition: Long, sampleCount: Int): Long {
        return if (abs(factor - 1.0f) < 0.0001f) samplePosition + sampleCount else samplePosition
    }
}

@UnstableApi
class FusionRenderersFactory(
    context: Context,
    private val gainProcessor: AudioProcessor
) : DefaultRenderersFactory(context) {
    override fun buildAudioSink(
        context: Context,
        enableFloatOutput: Boolean,
        enableAudioTrackPlaybackParams: Boolean
    ): AudioSink {
        val chain = DefaultAudioSink.DefaultAudioProcessorChain(gainProcessor)
        return DefaultAudioSink.Builder(context)
            .setAudioProcessorChain(chain)
            .setEnableFloatOutput(enableFloatOutput)
            .setEnableAudioTrackPlaybackParams(enableAudioTrackPlaybackParams)
            .build()
    }
}

@UnstableApi
fun createLoudnessGainProcessor(provider: LoudnessGainProvider): AudioProcessor =
    GainProcessor(provider)
