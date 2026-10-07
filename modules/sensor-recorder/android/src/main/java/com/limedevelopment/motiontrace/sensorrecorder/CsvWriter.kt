package com.limedevelopment.motiontrace.sensorrecorder

import java.io.BufferedWriter
import java.io.Closeable
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStreamWriter

/**
 * Buffered CSV writer for one recording. Not thread-safe: every call must come from the same thread.
 *
 * Row format: `sensor_timestamp_ns,time_utc_ns,seconds_elapsed,x,y,z`
 * - `sensor_timestamp_ns` is `SensorEvent.timestamp`, written unmodified;
 * - `time_utc_ns` is `sensor_timestamp_ns + utcOffsetNs` (offset captured at recording start);
 * - `seconds_elapsed` counts from the first row, printed as a fixed-point decimal with 9 digits.
 */
class CsvWriter(file: File, private val utcOffsetNs: Long) : Closeable {
  private val stream = FileOutputStream(file)
  private val out = BufferedWriter(OutputStreamWriter(stream, Charsets.UTF_8), BUFFER_SIZE)
  private val line = StringBuilder(128)
  private var firstTimestampNs = 0L
  private var hasRows = false

  init {
    out.write(HEADER)
  }

  fun write(timestampNs: Long, x: Float, y: Float, z: Float) {
    if (!hasRows) {
      firstTimestampNs = timestampNs
      hasRows = true
    }
    line.setLength(0)
    line.append(timestampNs).append(',')
      .append(timestampNs + utcOffsetNs).append(',')
    appendSeconds(line, timestampNs - firstTimestampNs)
    // StringBuilder.append(Float) is locale-independent and round-trips the exact float value.
    line.append(',').append(x)
      .append(',').append(y)
      .append(',').append(z)
      .append('\n')
    out.append(line)
  }

  /** Pushes buffered rows to the OS, so they survive an app crash. */
  fun flush() {
    out.flush()
  }

  override fun close() {
    out.flush()
    stream.fd.sync()
    out.close()
  }

  private fun appendSeconds(sb: StringBuilder, ns: Long) {
    var value = ns
    if (value < 0) {
      sb.append('-')
      value = -value
    }
    sb.append(value / NANOS_PER_SECOND).append('.')
    val fraction = (value % NANOS_PER_SECOND).toString()
    repeat(9 - fraction.length) { sb.append('0') }
    sb.append(fraction)
  }

  companion object {
    const val HEADER = "sensor_timestamp_ns,time_utc_ns,seconds_elapsed,x,y,z\n"
    private const val BUFFER_SIZE = 64 * 1024
    private const val NANOS_PER_SECOND = 1_000_000_000L
  }
}
