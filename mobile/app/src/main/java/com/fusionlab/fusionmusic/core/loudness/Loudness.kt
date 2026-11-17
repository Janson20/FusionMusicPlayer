package com.fusionlab.fusionmusic.core.loudness

import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.tan

/**
 * EBU R128 / ITU-R BS.1770-4 响度测算与增益计算。
 *
 * 纯 Kotlin、无 Android 依赖：解码侧只需要把 PCM 按帧喂进来，测试与本地
 * 文件分析共用同一套实现。K 加权系数按采样率现算（预畸变双线性变换），
 * 因此在 44.1 kHz / 48 kHz 等任意采样率上都成立。
 */
object LoudnessConstants {
    const val ANALYSIS_VERSION = 1
    const val DEFAULT_TARGET_LUFS = -14.0
    const val ABSOLUTE_GATE_LUFS = -70.0
    const val RELATIVE_GATE_LU = 10.0
    const val CALIBRATION_DB = -0.691
    const val BLOCK_SECONDS = 0.4
    const val BLOCK_STEP_SECONDS = 0.1
    const val MIN_BLOCK_SECONDS = 0.1
    const val DEFAULT_MAX_GAIN_DB = 12.0
    const val DEFAULT_MIN_GAIN_DB = -24.0
    const val DEFAULT_PEAK_CEILING = 0.891
    const val PARTIAL_PEAK_CEILING = 0.708
}

data class LoudnessResult(
    val loudnessLufs: Double?,
    val peak: Double,
    val analyzedSeconds: Double,
    val blocks: Int = 0,
    val gatedBlocks: Int = 0
) {
    val measurable: Boolean get() = loudnessLufs != null
}

private data class Biquad(
    val b0: Double,
    val b1: Double,
    val b2: Double,
    val a1: Double,
    val a2: Double
)

private fun highShelfCoeffs(rate: Int, f0: Double, gainDb: Double, q: Double, vbExp: Double): Biquad {
    val k = tan(Math.PI * f0 / rate)
    val vh = 10.0.pow(gainDb / 20.0)
    val vb = vh.pow(vbExp)
    val a0 = 1.0 + k / q + k * k
    return Biquad(
        (vh + vb * k / q + k * k) / a0,
        2.0 * (k * k - vh) / a0,
        (vh - vb * k / q + k * k) / a0,
        2.0 * (k * k - 1.0) / a0,
        (1.0 - k / q + k * k) / a0
    )
}

private fun highPassCoeffs(rate: Int, f0: Double, q: Double): Biquad {
    val k = tan(Math.PI * f0 / rate)
    val a0 = 1.0 + k / q + k * k
    return Biquad(
        1.0,
        -2.0,
        1.0,
        2.0 * (k * k - 1.0) / a0,
        (1.0 - k / q + k * k) / a0
    )
}

private fun kWeightingCoeffs(rate: Int): Pair<Biquad, Biquad> {
    require(rate > 0) { "采样率必须为正" }
    val nyquist = rate / 2.0
    val rlbF0 = min(38.13547087602444, nyquist * 0.5)
    val preF0 = min(1681.974450955533, nyquist * 0.9)
    return highPassCoeffs(rate, rlbF0, 0.5003270373238773) to
        highShelfCoeffs(rate, preF0, 3.999843853973347, 0.7071752369554196, 0.4996667741545416)
}

private class ChannelState {
    var x1 = 0.0
    var x2 = 0.0
    var y1 = 0.0
    var y2 = 0.0
    var u1 = 0.0
    var u2 = 0.0
    var v1 = 0.0
    var v2 = 0.0
    val segments = ArrayList<Double>()
    var current = 0.0
    var count = 0
    var peak = 0.0

    fun pushSample(xRaw: Double, stage1: Biquad, stage2: Biquad, step: Int) {
        val x = if (xRaw.isFinite() && abs(xRaw) < 1e30) xRaw else 0.0
        if (x != xRaw) {
            // 无效样本按 0 处理；峰值也不统计。
        } else {
            val a = abs(x)
            if (a > peak) peak = a
        }
        val y = stage1.b0 * x + stage1.b1 * x1 + stage1.b2 * x2 - stage1.a1 * y1 - stage1.a2 * y2
        x2 = x1
        x1 = x
        y2 = y1
        y1 = y
        val v = stage2.b0 * y + stage2.b1 * u1 + stage2.b2 * u2 - stage2.a1 * v1 - stage2.a2 * v2
        u2 = u1
        u1 = y
        v2 = v1
        v1 = v
        current += v * v
        count += 1
        if (count == step) {
            segments.add(current)
            current = 0.0
            count = 0
        }
    }
}

class LoudnessMeter(
    private val rate: Int,
    channels: Int = 1
) {
    private val step = max(1, (LoudnessConstants.BLOCK_STEP_SECONDS * rate).roundToInt())
    private val size = max(1, (LoudnessConstants.BLOCK_SECONDS * rate).roundToInt())
    private val perBlock = max(1, (size.toDouble() / step).roundToInt())
    private val stage1: Biquad
    private val stage2: Biquad
    private val states = ArrayList<ChannelState>()
    private var frames = 0L

    init {
        require(rate > 0)
        val coeffs = kWeightingCoeffs(rate)
        stage1 = coeffs.first
        stage2 = coeffs.second
        repeat(channels.coerceIn(1, 2)) { states.add(ChannelState()) }
    }

    /**
     * 喂入交错 PCM。每个样本应在 [-1, 1] 附近；更多声道只取前两个，
     * 与标准「各声道均方相加」的口径一致（环绕声道增益这里不处理）。
     */
    fun feedInterleaved(data: FloatArray, channels: Int, offset: Int = 0, length: Int = data.size) {
        val usableChannels = channels.coerceIn(1, 2)
        if (usableChannels <= 0) return
        val end = min(data.size, offset + length)
        var index = offset
        while (index < end) {
            for (channel in 0 until usableChannels) {
                if (index >= end) break
                states[channel].pushSample(data[index].toDouble(), stage1, stage2, step)
                index += 1
            }
            // 多于两个声道时跳过剩余声道，但要保持帧对齐。
            if (channels > usableChannels) {
                index += channels - usableChannels
            }
            frames += 1
        }
    }

    val analyzedSeconds: Double get() = frames.toDouble() / rate.toDouble()

    val peak: Double
        get() = states.maxOfOrNull { it.peak } ?: 0.0

    fun result(): LoudnessResult {
        val sums = blockSums()
        val (blocks, gated) = gate(sums)
        val loudness = when {
            blocks.isEmpty() -> shortLoudness()
            gated.isEmpty() -> null
            else -> {
                val mean = gated.average()
                if (mean <= 0.0) null else LoudnessConstants.CALIBRATION_DB + 10.0 * log10(mean)
            }
        }
        return LoudnessResult(loudness, peak, analyzedSeconds, blocks.size, gated.size)
    }

    private fun blockSums(): List<Double> {
        var summed: MutableList<Double>? = null
        for (state in states) {
            val segments = state.segments
            val count = segments.size - perBlock + 1
            if (count <= 0) continue
            val prefix = DoubleArray(segments.size + 1)
            var acc = 0.0
            for (i in segments.indices) {
                acc += segments[i]
                prefix[i + 1] = acc
            }
            val window = MutableList(count) { i -> prefix[i + perBlock] - prefix[i] }
            val current = summed
            if (current == null) {
                summed = window
            } else {
                val size = min(current.size, window.size)
                for (i in 0 until size) current[i] += window[i]
                while (current.size > size) current.removeAt(current.size - 1)
            }
        }
        val values = summed ?: return emptyList()
        val samplesPerBlock = (perBlock * step).toDouble()
        return values.map { it / samplesPerBlock }
    }

    private fun gate(energies: List<Double>): Pair<List<Double>, List<Double>> {
        if (energies.isEmpty()) return emptyList<Double>() to emptyList()
        val absolute = 10.0.pow((LoudnessConstants.ABSOLUTE_GATE_LUFS - LoudnessConstants.CALIBRATION_DB) / 10.0)
        val kept = energies.filter { it >= absolute }
        if (kept.isEmpty()) return energies to emptyList()
        val meanSquare = kept.average()
        if (meanSquare <= 0.0) return energies to emptyList()
        val relative = LoudnessConstants.CALIBRATION_DB + 10.0 * log10(meanSquare) - LoudnessConstants.RELATIVE_GATE_LU
        val gated = kept.filter {
            it > 0.0 && LoudnessConstants.CALIBRATION_DB + 10.0 * log10(it) > relative
        }
        return energies to gated
    }

    private fun shortLoudness(): Double? {
        if (analyzedSeconds < LoudnessConstants.MIN_BLOCK_SECONDS) return null
        var total = 0.0
        var counted = 0
        for (state in states) {
            val energy = state.segments.sum() + state.current
            val samples = state.segments.size * step + state.count
            if (samples > 0) {
                total += energy / samples
                counted += 1
            }
        }
        if (counted == 0 || total <= 0.0) return null
        return LoudnessConstants.CALIBRATION_DB + 10.0 * log10(total)
    }
}

object LoudnessGain {
    fun dbToRatio(db: Double): Double = 10.0.pow(db / 20.0)

    fun ratioToDb(ratio: Double): Double = if (ratio > 0.0) 20.0 * log10(ratio) else -120.0

    fun gainDb(
        loudnessLufs: Double?,
        peak: Double,
        targetLufs: Double = LoudnessConstants.DEFAULT_TARGET_LUFS,
        preampDb: Double = 0.0,
        allowBoost: Boolean = true,
        peakCeiling: Double = LoudnessConstants.DEFAULT_PEAK_CEILING,
        maxGainDb: Double = LoudnessConstants.DEFAULT_MAX_GAIN_DB,
        minGainDb: Double = LoudnessConstants.DEFAULT_MIN_GAIN_DB
    ): Double {
        if (loudnessLufs == null || !loudnessLufs.isFinite()) return 0.0
        var want = targetLufs - loudnessLufs + preampDb
        if (!allowBoost) want = min(want, 0.0)
        if (peak > 0.0 && peakCeiling > 0.0) {
            want = min(want, 20.0 * log10(peakCeiling / peak))
        } else {
            want = min(want, 0.0)
        }
        return max(minGainDb, min(maxGainDb, want))
    }

    fun describe(db: Double): String {
        if (abs(db) < 0.05) return "不调整"
        return String.format(java.util.Locale.US, "%+.1f dB", db)
    }
}
