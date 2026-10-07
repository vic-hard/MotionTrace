package com.limedevelopment.motiontrace.sensorrecorder

/**
 * Counters over the samples written so far. Immutable on purpose: the recorder thread (the only
 * writer) publishes a new snapshot per sample through a `@Volatile` reference, so readers on other
 * threads always see a consistent set of values.
 */
internal data class SampleStats(
  val count: Long = 0,
  val firstTimestampNs: Long = 0,
  val lastTimestampNs: Long = 0,
  /** Largest interval between consecutive samples. */
  val maxIntervalNs: Long = 0,
) {
  /** Average rate, from sensor timestamps. */
  val rateHz: Double
    get() {
      val spanNs = lastTimestampNs - firstTimestampNs
      return if (count > 1 && spanNs > 0) (count - 1) * 1e9 / spanNs else 0.0
    }

  fun plus(timestampNs: Long): SampleStats =
    if (count == 0L) {
      SampleStats(1, timestampNs, timestampNs, 0)
    } else {
      SampleStats(
        count = count + 1,
        firstTimestampNs = firstTimestampNs,
        lastTimestampNs = timestampNs,
        maxIntervalNs = maxOf(maxIntervalNs, timestampNs - lastTimestampNs),
      )
    }
}
