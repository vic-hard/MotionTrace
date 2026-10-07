package com.limedevelopment.motiontrace.sensorrecorder

import android.hardware.Sensor
import android.os.Build
import org.json.JSONObject
import java.io.File
import java.io.IOException

/**
 * Writes a recording's JSON metadata: once at start, and again with results at stop.
 * A file without `result` means the recording was cut off.
 */
internal class MetadataWriter(
  private val file: File,
  private val csvFileName: String,
  private val sensor: Sensor,
  private val mode: RecordingMode,
  private val startClock: ClockPair,
) {
  fun writeStart() = write(startJson())

  fun writeStop(stopClock: ClockPair, status: RecorderStatus, stats: SampleStats) = write(
    startJson()
      .put("clockAtStop", stopClock.toJson())
      .put("result", JSONObject()
        .put("sampleCount", status.sampleCount)
        .put("firstSensorTimestampNs", stats.firstTimestampNs)
        .put("lastSensorTimestampNs", stats.lastTimestampNs)
        .put("durationSec", status.durationSec)
        .put("rateHz", status.rateHz)
        .put("maxIntervalMs", status.maxIntervalMs)
        .put("error", status.error ?: JSONObject.NULL))
  )

  private fun startJson(): JSONObject = JSONObject()
    .put("formatVersion", FORMAT_VERSION)
    .put("csvFile", csvFileName)
    .put("device", JSONObject()
      .put("manufacturer", Build.MANUFACTURER)
      .put("brand", Build.BRAND)
      .put("model", Build.MODEL)
      .put("device", Build.DEVICE)
      .put("androidVersion", Build.VERSION.RELEASE)
      .put("sdkInt", Build.VERSION.SDK_INT))
    .put("sensor", JSONObject()
      .put("type", sensor.stringType)
      .put("name", sensor.name)
      .put("vendor", sensor.vendor)
      .put("version", sensor.version)
      .put("minDelayUs", sensor.minDelay)
      .put("maxDelayUs", sensor.maxDelay)
      .put("fifoMaxEventCount", sensor.fifoMaxEventCount)
      .put("fifoReservedEventCount", sensor.fifoReservedEventCount)
      .put("resolution", sensor.resolution)
      .put("maximumRange", sensor.maximumRange)
      .put("powerMa", sensor.power)
      .put("isWakeUpSensor", sensor.isWakeUpSensor))
    .put("recording", JSONObject()
      .put("mode", mode.id)
      .put("requestedSamplingPeriodUs", mode.samplingPeriodUs)
      .put("maxReportLatencyUs", 0))
    .put("clockAtStart", startClock.toJson())

  // Write-then-rename, so a crash never leaves a half-written file.
  private fun write(json: JSONObject) {
    val tmp = File(file.path + ".tmp")
    tmp.writeText(json.toString(2))
    if (!tmp.renameTo(file)) throw IOException("Cannot write $file")
  }

  companion object {
    private const val FORMAT_VERSION = 1
  }
}
