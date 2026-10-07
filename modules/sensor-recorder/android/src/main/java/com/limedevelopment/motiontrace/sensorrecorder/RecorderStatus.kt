package com.limedevelopment.motiontrace.sensorrecorder

data class RecorderStatus(
  val isRecording: Boolean,
  val mode: RecordingMode?,
  val csvPath: String?,
  /** Wall time since start, in seconds. */
  val durationSec: Double,
  val sampleCount: Long,
  /** Average rate over all samples, from sensor timestamps. */
  val rateHz: Double,
  /** Largest interval between consecutive samples. */
  val maxIntervalMs: Double,
  val error: String?,
) {
  companion object {
    val IDLE = RecorderStatus(false, null, null, 0.0, 0, 0.0, 0.0, null)
  }
}
