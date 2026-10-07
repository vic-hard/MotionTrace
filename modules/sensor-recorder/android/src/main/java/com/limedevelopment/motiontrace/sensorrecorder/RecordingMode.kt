package com.limedevelopment.motiontrace.sensorrecorder

import android.hardware.SensorManager

enum class RecordingMode(
  val id: String,
  /** Microseconds, as in SensorManager.registerListener. */
  val samplingPeriodUs: Int,
) {
  HZ_100("100hz", 10_000),

  /** Fastest rate the sensor supports; above 200 Hz relies on HIGH_SAMPLING_RATE_SENSORS. */
  MAX("max", SensorManager.SENSOR_DELAY_FASTEST);

  companion object {
    fun fromId(id: String): RecordingMode? = entries.firstOrNull { it.id == id }
  }
}
