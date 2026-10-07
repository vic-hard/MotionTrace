package com.limedevelopment.motiontrace.sensorrecorder

/** One recording in [RecordingStore], summarised from its metadata. */
data class RecordingInfo(
  /** File name without extension, shared by the CSV and the JSON. */
  val id: String,
  val mode: String?,
  val startedAtMs: Long?,
  /** CSV + JSON. */
  val sizeBytes: Long,
  /** False if the metadata has no `result`: the recording was cut off. */
  val isComplete: Boolean,
  // From `result`, so only for complete recordings.
  val durationSec: Double?,
  val sampleCount: Long?,
  val rateHz: Double?,
)
