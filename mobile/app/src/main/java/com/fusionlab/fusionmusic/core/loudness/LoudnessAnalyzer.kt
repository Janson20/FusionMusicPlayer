package com.fusionlab.fusionmusic.core.loudness

import android.content.Context
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import android.os.SystemClock
import com.fusionlab.fusionmusic.core.util.AppLog
import kotlinx.coroutines.ensureActive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.TimeUnit
import kotlin.coroutines.coroutineContext
import kotlin.math.min

data class AnalysisInput(
    val location: String,
    val headers: Map<String, String> = emptyMap(),
    val cookies: Map<String, String> = emptyMap(),
    val local: Boolean = false
)

data class DecodedAnalysis(
    val result: LoudnessResult,
    val complete: Boolean
)

/**
 * 用 MediaExtractor + MediaCodec 把音频解码成 PCM，再交给 [LoudnessMeter]。
 *
 * 在线地址先经 OkHttp 下载前 24 MB 到临时文件：一方面能带上各音源要求的
 * Referer / Cookie（MediaExtractor 的请求头能力有限），另一方面下载超时、
 * 取消与断点都由我们控制。24 MB 覆盖绝大多数 320k 曲目的前几分钟，足够
 * 做门限积分响度。
 */
class LoudnessAnalyzer(
    private val context: Context,
    private val log: AppLog
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    suspend fun analyze(
        input: AnalysisInput,
        maxSeconds: Int = 0,
        timeoutSeconds: Int = 180
    ): DecodedAnalysis? {
        val location = input.location.trim()
        if (location.isEmpty()) return null
        if (location.startsWith("http://") || location.startsWith("https://")) {
            val temp = downloadPartial(input) ?: return null
            return try {
                decode(temp.absolutePath, null, maxSeconds, timeoutSeconds)
            } finally {
                temp.delete()
            }
        }
        val uri = if (location.startsWith("content://")) Uri.parse(location) else null
        val path = if (uri == null) {
            if (location.startsWith("file://")) Uri.parse(location).path ?: location else location
        } else {
            ""
        }
        return decode(path, uri, maxSeconds, timeoutSeconds)
    }

    private fun downloadPartial(input: AnalysisInput): File? {
        val dir = File(context.filesDir, "data/cache/loudness").apply { mkdirs() }
        val temp = File(dir, "analysis-" + System.nanoTime() + ".part")
        val builder = Request.Builder().url(input.location)
        for ((name, value) in input.headers) builder.header(name, value)
        if (input.cookies.isNotEmpty()) {
            builder.header("Cookie", input.cookies.entries.joinToString("; ") { it.key + "=" + it.value })
        }
        if (!input.headers.keys.any { it.equals("User-Agent", ignoreCase = true) }) {
            builder.header("User-Agent", "Mozilla/5.0 (Linux; Android 14) FusionMusic/1.0")
        }
        var written = 0L
        return try {
            client.newCall(builder.build()).execute().use { response ->
                if (!response.isSuccessful) return null
                val body = response.body ?: return null
                FileOutputStream(temp).use { output ->
                    body.byteStream().use { stream ->
                        val buffer = ByteArray(64 * 1024)
                        while (written < MAX_DOWNLOAD_BYTES) {
                            val read = stream.read(buffer)
                            if (read <= 0) break
                            val keep = min(read.toLong(), MAX_DOWNLOAD_BYTES - written).toInt()
                            output.write(buffer, 0, keep)
                            written += keep
                            if (keep < read) break
                        }
                        output.fd.sync()
                    }
                }
            }
            if (written <= 0L) {
                temp.delete()
                null
            } else {
                temp
            }
        } catch (error: Exception) {
            log.w("LoudnessAnalyzer", "download failed: " + error.message)
            temp.delete()
            null
        }
    }

    private suspend fun decode(
        path: String,
        uri: Uri?,
        maxSeconds: Int,
        timeoutSeconds: Int
    ): DecodedAnalysis? {
        val extractor = MediaExtractor()
        var codec: MediaCodec? = null
        var meter: LoudnessMeter? = null
        var meterRate = 0
        var meterChannels = 0
        var pcmEncoding = android.media.AudioFormat.ENCODING_PCM_16BIT
        var complete = false
        var limitHit = false
        var timedOut = false
        val started = SystemClock.elapsedRealtime()
        try {
            if (uri != null) {
                extractor.setDataSource(context, uri, null)
            } else {
                if (path.isBlank() || !File(path).exists()) return null
                extractor.setDataSource(path)
            }
            val trackIndex = selectAudioTrack(extractor)
            if (trackIndex < 0) return null
            extractor.selectTrack(trackIndex)
            val format = extractor.getTrackFormat(trackIndex)
            val mime = format.getString(MediaFormat.KEY_MIME) ?: return null
            codec = MediaCodec.createDecoderByType(mime)
            codec.configure(format, null, null, 0)
            codec.start()

            val info = MediaCodec.BufferInfo()
            var inputDone = false
            var outputDone = false
            while (!outputDone) {
                coroutineContext.ensureActive()
                if ((SystemClock.elapsedRealtime() - started) / 1000 > timeoutSeconds.coerceAtLeast(5)) {
                    timedOut = true
                    break
                }
                if (!inputDone) {
                    val inputIndex = codec.dequeueInputBuffer(10_000)
                    if (inputIndex >= 0) {
                        val input = codec.getInputBuffer(inputIndex)
                        if (input == null) {
                            codec.queueInputBuffer(inputIndex, 0, 0, 0, 0)
                        } else {
                            val size = extractor.readSampleData(input, 0)
                            if (size < 0) {
                                codec.queueInputBuffer(inputIndex, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                inputDone = true
                            } else {
                                codec.queueInputBuffer(inputIndex, 0, size, extractor.sampleTime, 0)
                                extractor.advance()
                            }
                        }
                    }
                }

                when (val outputIndex = codec.dequeueOutputBuffer(info, 10_000)) {
                    MediaCodec.INFO_TRY_AGAIN_LATER -> Unit
                    MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                        val outputFormat = codec.outputFormat
                        val rate = intOr(outputFormat, MediaFormat.KEY_SAMPLE_RATE, 44100)
                        val channels = intOr(outputFormat, MediaFormat.KEY_CHANNEL_COUNT, 2)
                        if (meter == null || meterRate != rate || meterChannels != channels) {
                            meter = LoudnessMeter(rate, channels)
                            meterRate = rate
                            meterChannels = channels
                            pcmEncoding = intOr(outputFormat, MediaFormat.KEY_PCM_ENCODING, android.media.AudioFormat.ENCODING_PCM_16BIT)
                        }
                    }
                    else -> {
                        if (outputIndex >= 0) {
                            if (meter == null) {
                                val rate = intOr(format, MediaFormat.KEY_SAMPLE_RATE, 44100)
                                val channels = intOr(format, MediaFormat.KEY_CHANNEL_COUNT, 2)
                                meter = LoudnessMeter(rate, channels)
                                meterRate = rate
                                meterChannels = channels
                                pcmEncoding = intOr(format, MediaFormat.KEY_PCM_ENCODING, android.media.AudioFormat.ENCODING_PCM_16BIT)
                            }
                            if (info.size > 0) {
                                val buffer = codec.getOutputBuffer(outputIndex)
                                if (buffer != null) {
                                    val samples = toFloatSamples(buffer, info, pcmEncoding)
                                    meter?.feedInterleaved(samples, meterChannels)
                                }
                            }
                            codec.releaseOutputBuffer(outputIndex, false)
                            if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outputDone = true
                            val limit = maxSeconds
                            if (limit > 0 && (meter?.analyzedSeconds ?: 0.0) >= limit) {
                                limitHit = true
                                outputDone = true
                            }
                        }
                    }
                }
            }
            complete = !limitHit && !timedOut
            val result = meter?.result() ?: return null
            return DecodedAnalysis(result, complete)
        } catch (error: kotlinx.coroutines.CancellationException) {
            throw error
        } catch (error: Exception) {
            log.w("LoudnessAnalyzer", "decode failed: " + error.message)
            return null
        } finally {
            try {
                codec?.stop()
            } catch (_: Exception) {
            }
            try {
                codec?.release()
            } catch (_: Exception) {
            }
            extractor.release()
        }
    }

    private fun selectAudioTrack(extractor: MediaExtractor): Int {
        for (index in 0 until extractor.trackCount) {
            val mime = extractor.getTrackFormat(index).getString(MediaFormat.KEY_MIME) ?: continue
            if (mime.startsWith("audio/")) return index
        }
        return -1
    }

    private fun intOr(format: MediaFormat, key: String, fallback: Int): Int {
        return try {
            if (format.containsKey(key)) format.getInteger(key) else fallback
        } catch (_: Exception) {
            fallback
        }
    }

    private fun toFloatSamples(
        buffer: ByteBuffer,
        info: MediaCodec.BufferInfo,
        encoding: Int
    ): FloatArray {
        val byteCount = info.size
        if (byteCount <= 0) return FloatArray(0)
        val copy = buffer.duplicate()
        copy.position(info.offset)
        copy.limit(info.offset + info.size)
        copy.order(ByteOrder.LITTLE_ENDIAN)
        return when (encoding) {
            android.media.AudioFormat.ENCODING_PCM_FLOAT -> {
                val floats = FloatArray(byteCount / 4)
                copy.asFloatBuffer().get(floats)
                floats
            }
            android.media.AudioFormat.ENCODING_PCM_8BIT -> {
                val out = FloatArray(byteCount)
                for (i in 0 until byteCount) {
                    out[i] = ((copy.get(i).toInt() and 0xFF) - 128) / 128f
                }
                out
            }
            android.media.AudioFormat.ENCODING_PCM_32BIT -> {
                val ints = IntArray(byteCount / 4)
                copy.asIntBuffer().get(ints)
                FloatArray(ints.size) { ints[it] / 2147483648f }
            }
            android.media.AudioFormat.ENCODING_PCM_24BIT_PACKED -> {
                val frames = byteCount / 3
                val out = FloatArray(frames)
                for (i in 0 until frames) {
                    val base = i * 3
                    val value = (copy.get(base).toInt() and 0xFF) or
                        ((copy.get(base + 1).toInt() and 0xFF) shl 8) or
                        (copy.get(base + 2).toInt() shl 16)
                    out[i] = value / 8388608f
                }
                out
            }
            else -> {
                val shorts = ShortArray(byteCount / 2)
                copy.asShortBuffer().get(shorts)
                FloatArray(shorts.size) { shorts[it] / 32768f }
            }
        }
    }

    companion object {
        private const val MAX_DOWNLOAD_BYTES = 24L * 1024L * 1024L
    }
}
