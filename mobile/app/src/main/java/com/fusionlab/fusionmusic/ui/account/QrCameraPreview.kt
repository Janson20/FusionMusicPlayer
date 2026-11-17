package com.fusionlab.fusionmusic.ui.account

import android.os.Handler
import android.os.Looper
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.Result
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

@Composable
internal fun QrCameraPreview(
    scanKey: Int,
    onQr: (String) -> Unit,
    onFailure: (String) -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val previewView = remember {
        PreviewView(context).apply {
            scaleType = PreviewView.ScaleType.FILL_CENTER
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
        }
    }
    DisposableEffect(scanKey, lifecycleOwner) {
        val executor = Executors.newSingleThreadExecutor()
        val future = ProcessCameraProvider.getInstance(context)
        val analyzer = QrAnalyzer(onQr)
        var disposed = false
        val listener = Runnable {
            if (disposed || !future.isDone) return@Runnable
            try {
                val provider = future.get()
                val preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(previewView.surfaceProvider)
                }
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setTargetResolution(Size(1280, 720))
                    .build()
                analysis.setAnalyzer(executor, analyzer)
                val selector = when {
                    provider.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA) -> CameraSelector.DEFAULT_BACK_CAMERA
                    provider.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA) -> CameraSelector.DEFAULT_FRONT_CAMERA
                    else -> throw IllegalStateException("no camera")
                }
                provider.unbindAll()
                provider.bindToLifecycle(lifecycleOwner, selector, preview, analysis)
            } catch (_: Exception) {
                if (!disposed) onFailure("相机启动失败，请检查是否被其他应用占用")
            }
        }
        future.addListener(listener, ContextCompat.getMainExecutor(context))
        onDispose {
            disposed = true
            analyzer.stop()
            try {
                if (future.isDone) future.get().unbindAll()
            } catch (_: Exception) {
                // 相机已经不可用时不需要再报错
            }
            executor.shutdown()
        }
    }

    AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize())
}

private class QrAnalyzer(
    private val onQr: (String) -> Unit
) : ImageAnalysis.Analyzer {
    private val done = AtomicBoolean(false)
    private val main = Handler(Looper.getMainLooper())
    private val reader = QRCodeReader()
    private val hints = mapOf(
        DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
        DecodeHintType.TRY_HARDER to true
    )

    override fun analyze(image: ImageProxy) {
        try {
            if (done.get()) return
            val text = decode(image) ?: return
            if (!text.startsWith("fusionmusic://login-transfer")) return
            if (done.compareAndSet(false, true)) {
                main.post { onQr(text) }
            }
        } catch (_: Exception) {
            // 单帧解码失败是常态，继续等下一帧
        } finally {
            image.close()
        }
    }

    fun stop() {
        done.set(true)
    }

    private fun decode(image: ImageProxy): String? {
        val plane = image.planes.firstOrNull() ?: return null
        val buffer = plane.buffer
        val width = image.width
        val height = image.height
        if (width <= 0 || height <= 0) return null
        val rowStride = plane.rowStride
        val pixelStride = plane.pixelStride
        if (rowStride <= 0 || pixelStride <= 0) return null
        val data = ByteArray(width * height)
        val row = ByteArray(rowStride)
        var output = 0
        for (y in 0 until height) {
            val start = y * rowStride
            if (start >= buffer.limit()) break
            buffer.position(start)
            val count = minOf(rowStride, buffer.remaining())
            buffer.get(row, 0, count)
            var source = 0
            for (x in 0 until width) {
                if (source >= count) break
                data[output++] = row[source]
                source += pixelStride
            }
        }
        if (output != data.size) return null
        val rotated = rotate(data, width, height, image.imageInfo.rotationDegrees)
        val luminance = PlanarYUVLuminanceSource(
            rotated.data,
            rotated.width,
            rotated.height,
            0,
            0,
            rotated.width,
            rotated.height,
            false
        )
        val result: Result = reader.decode(BinaryBitmap(HybridBinarizer(luminance)), hints)
        return result.text
    }

    private data class Rotated(val data: ByteArray, val width: Int, val height: Int)

    private fun rotate(data: ByteArray, width: Int, height: Int, degrees: Int): Rotated {
        if (degrees % 360 == 0) return Rotated(data, width, height)
        val output = ByteArray(data.size)
        if (degrees % 360 == 180) {
            for (y in 0 until height) {
                for (x in 0 until width) {
                    output[(height - 1 - y) * width + (width - 1 - x)] = data[y * width + x]
                }
            }
            return Rotated(output, width, height)
        }
        // 90 / 270：输出宽高互换；按顺时针旋转。
        for (y in 0 until height) {
            for (x in 0 until width) {
                val source = data[y * width + x]
                if (degrees % 360 == 90) {
                    output[x * height + (height - 1 - y)] = source
                } else {
                    output[(width - 1 - x) * height + y] = source
                }
            }
        }
        return Rotated(output, height, width)
    }
}
