package com.limedevelopment.motiontrace.sensorrecorder

import android.content.Context
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.functions.Queues
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.io.File

private const val STATUS_EVENT = "onStatus"

/** Thin Expo wrapper: logic lives in [RecorderService] and [RecordingStore]. */
class SensorRecorderModule : Module() {
  private val statusListener: (RecorderStatus) -> Unit = { sendEvent(STATUS_EVENT, it.toMap()) }

  private val context: Context
    get() = appContext.reactContext?.applicationContext ?: throw Exceptions.ReactContextLost()

  private val store: RecordingStore
    get() = RecordingStore.default(context)

  override fun definition() = ModuleDefinition {
    Name("SensorRecorder")

    Events(STATUS_EVENT)

    // The recording lives in RecorderService and survives JS reloads: a new module instance
    // just picks up its status.
    OnCreate {
      RecorderService.addStatusListener(statusListener)
    }

    OnDestroy {
      RecorderService.removeStatusListener(statusListener)
    }

    AsyncFunction("start") { mode: String ->
      val recordingMode = RecordingMode.fromId(mode) ?: throw InvalidModeException(mode)
      if (RecorderService.isRecording) throw AlreadyRecordingException()
      RecorderService.start(context, recordingMode).toMap()
    }

    AsyncFunction("stop") {
      RecorderService.stop().toMap()
    }

    Function("getStatus") {
      RecorderService.status().toMap()
    }

    // The recording in progress is left out: it is still being written.
    AsyncFunction("listRecordings") {
      store.list().filter { it.id != activeRecordingId() }.map { it.toMap() }
    }

    AsyncFunction("shareRecordings") { ids: List<String> ->
      val activity = appContext.currentActivity ?: throw Exceptions.MissingActivity()
      val files = ids.flatMap { store.files(it) }
      activity.startActivity(RecordingSharing.chooserIntent(activity, files))
    }.runOnQueue(Queues.MAIN)

    AsyncFunction("deleteRecordings") { ids: List<String> ->
      if (activeRecordingId() in ids) throw RecordingInProgressException()
      ids.forEach { store.delete(it) }
    }
  }

  private fun activeRecordingId(): String? =
    RecorderService.status().takeIf { it.isRecording }?.csvPath?.let { File(it).nameWithoutExtension }

  private fun RecorderStatus.toMap(): Map<String, Any?> = mapOf(
    "isRecording" to isRecording,
    "mode" to mode?.id,
    "csvPath" to csvPath,
    "durationSec" to durationSec,
    "sampleCount" to sampleCount,
    "rateHz" to rateHz,
    "maxIntervalMs" to maxIntervalMs,
    "gapCount" to gapCount,
    "error" to error,
  )

  private fun RecordingInfo.toMap(): Map<String, Any?> = mapOf(
    "id" to id,
    "mode" to mode,
    "startedAtMs" to startedAtMs,
    "sizeBytes" to sizeBytes,
    "isComplete" to isComplete,
    "durationSec" to durationSec,
    "sampleCount" to sampleCount,
    "rateHz" to rateHz,
  )
}
