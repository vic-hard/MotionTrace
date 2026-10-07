package com.limedevelopment.motiontrace.sensorrecorder

import android.content.Context
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.io.File

private const val STATUS_EVENT = "onStatus"

/** Thin Expo wrapper: all recording logic lives in [SensorRecorder]. */
class SensorRecorderModule : Module() {
  // start/stop run on the shared AsyncFunction thread, getStatus on the JS thread.
  @Volatile private var recorder: SensorRecorder? = null

  private val context: Context
    get() = appContext.reactContext?.applicationContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("SensorRecorder")

    Events(STATUS_EVENT)

    AsyncFunction("start") { mode: String ->
      val recordingMode = RecordingMode.fromId(mode) ?: throw InvalidModeException(mode)
      if (recorder?.isRecording == true) throw AlreadyRecordingException()
      val newRecorder = SensorRecorder(context, recordingMode, recordingsDir(context)) {
        sendEvent(STATUS_EVENT, it.toMap())
      }
      // Keep it before start(): stop() must reach it whatever start() throws, and a failed
      // start leaves its error in getStatus().
      recorder = newRecorder
      newRecorder.start()
      newRecorder.status().toMap()
    }

    AsyncFunction("stop") {
      (recorder?.stop() ?: RecorderStatus.IDLE).toMap()
    }

    Function("getStatus") {
      (recorder?.status() ?: RecorderStatus.IDLE).toMap()
    }

    OnDestroy {
      recorder?.stop()
    }
  }

  private fun recordingsDir(context: Context): File =
    // App-specific external storage: no permissions needed, reachable with `adb pull`.
    File(context.getExternalFilesDir(null) ?: context.filesDir, "recordings")

  private fun RecorderStatus.toMap(): Map<String, Any?> = mapOf(
    "isRecording" to isRecording,
    "mode" to mode?.id,
    "csvPath" to csvPath,
    "durationSec" to durationSec,
    "sampleCount" to sampleCount,
    "rateHz" to rateHz,
    "maxIntervalMs" to maxIntervalMs,
    "error" to error,
  )
}
