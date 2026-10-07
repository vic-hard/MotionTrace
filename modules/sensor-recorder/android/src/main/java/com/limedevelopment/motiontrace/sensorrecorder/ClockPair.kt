package com.limedevelopment.motiontrace.sensorrecorder

import android.os.SystemClock
import org.json.JSONObject

/** `elapsedRealtimeNanos` (the `SensorEvent.timestamp` base) and wall-clock time, read back to back. */
internal class ClockPair(val elapsedRealtimeNs: Long, val currentTimeMs: Long) {
  val utcOffsetNs get() = currentTimeMs * 1_000_000 - elapsedRealtimeNs

  fun toJson(): JSONObject = JSONObject()
    .put("elapsedRealtimeNanos", elapsedRealtimeNs)
    .put("currentTimeMillis", currentTimeMs)
    .put("utcOffsetNs", utcOffsetNs)

  companion object {
    fun capture(): ClockPair {
      val before = SystemClock.elapsedRealtimeNanos()
      val wall = System.currentTimeMillis()
      val after = SystemClock.elapsedRealtimeNanos()
      return ClockPair(before + (after - before) / 2, wall)
    }
  }
}
