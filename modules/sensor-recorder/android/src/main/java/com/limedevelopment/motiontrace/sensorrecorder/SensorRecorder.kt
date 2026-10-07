package com.limedevelopment.motiontrace.sensorrecorder

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.HandlerThread
import android.os.Process
import android.os.SystemClock
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Records `TYPE_GRAVITY` into `<name>.csv` plus `<name>.json` metadata in [outputDir].
 *
 * One instance is one recording: [start] once, [stop] once. Sensor events, CSV writes and the
 * once-per-second flush/status tick all run on a private [HandlerThread]. No Expo dependencies,
 * so the class can be driven by the Expo module now and by a foreground service later.
 */
class SensorRecorder(
  context: Context,
  val mode: RecordingMode,
  private val outputDir: File,
  /** Called on start, every second while recording (on the recorder thread) and once after stopping. */
  private val onStatus: ((RecorderStatus) -> Unit)? = null,
) : SensorEventListener {
  private enum class State { IDLE, RECORDING, STOPPED }

  private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
  private var thread: HandlerThread? = null
  private var handler: Handler? = null
  private var writer: CsvWriter? = null
  private var csvFile: File? = null
  private var metadata: MetadataWriter? = null
  private var stopClock: ClockPair? = null
  private var nextTickUptimeMs = 0L

  // Lifecycle: written by the caller of start()/stop() and by the recorder thread on failure.
  // Kept as separate fields: state transitions go through @Synchronized markStopped().
  @Volatile private var state = State.IDLE
  @Volatile private var error: String? = null
  @Volatile private var startElapsedNs = 0L
  @Volatile private var stopElapsedNs = 0L

  // Written only on the recorder thread, read from any thread by status().
  @Volatile private var stats = SampleStats()

  val isRecording get() = state == State.RECORDING

  /** Opens the files and subscribes to the sensor. Throws if the recording can't be started. */
  @Synchronized
  fun start() {
    check(state == State.IDLE) { "A SensorRecorder can only be started once" }
    try {
      val sensor = findSensor()
      val clock = ClockPair.capture()
      openFiles(sensor, clock)
      val handler = startThread()
      startElapsedNs = clock.elapsedRealtimeNs
      // Before subscribing: onSensorChanged drops events unless the state is RECORDING.
      state = State.RECORDING
      // Keep subscribe() the last step that can throw: once events flow, the recorder thread
      // writes to the CSV, and abortStart() must not close it from this thread.
      subscribe(sensor, handler)
      scheduleTicks(handler)
    } catch (e: Exception) {
      abortStart(e)
      throw e
    }
    onStatus?.invoke(status())
  }

  private fun findSensor(): Sensor =
    sensorManager.getDefaultSensor(Sensor.TYPE_GRAVITY)
      ?: throw IllegalStateException("This device has no gravity sensor")

  /** Creates the CSV and the initial metadata, named after the start time and mode. */
  private fun openFiles(sensor: Sensor, clock: ClockPair) {
    if (!outputDir.isDirectory && !outputDir.mkdirs()) {
      throw IOException("Cannot create $outputDir")
    }
    val stamp = SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.US).format(Date(clock.currentTimeMs))
    val baseName = "gravity_${stamp}_${mode.id}"
    val csv = File(outputDir, "$baseName.csv")
    csvFile = csv
    writer = CsvWriter(csv, clock.utcOffsetNs)
    metadata = MetadataWriter(File(outputDir, "$baseName.json"), csv.name, sensor, mode, clock)
      .apply { writeStart() }
  }

  private fun startThread(): Handler {
    val thread = HandlerThread(
      "SensorRecorder",
      Process.THREAD_PRIORITY_URGENT_DISPLAY
    ).apply { start() }

    this.thread = thread
    return Handler(thread.looper).also { handler = it }
  }

  private fun subscribe(sensor: Sensor, handler: Handler) {
    // maxReportLatencyUs = 0: deliver every event immediately, no hardware batching.
    if (!sensorManager.registerListener(this, sensor, mode.samplingPeriodUs, 0, handler)) {
      throw IllegalStateException("SensorManager.registerListener failed")
    }
  }

  private fun scheduleTicks(handler: Handler) {
    nextTickUptimeMs = SystemClock.uptimeMillis() + STATUS_INTERVAL_MS
    handler.postAtTime(tick, nextTickUptimeMs)
  }

  /** Undoes whatever part of start() succeeded. Files already created stay on disk. */
  private fun abortStart(e: Exception) {
    state = State.STOPPED
    error = e.message ?: e.toString()
    sensorManager.unregisterListener(this)
    thread?.quit()
    runCatching { writer?.close() }
  }

  /** Unsubscribes, flushes and closes the files. Safe to call more than once. */
  fun stop(): RecorderStatus {
    if (!markStopped()) return status()
    sensorManager.unregisterListener(this)
    val thread = thread!!
    handler!!.removeCallbacks(tick)
    // Finish on the recorder thread, after any events already queued there.
    handler!!.post { finish() }
    thread.quitSafely()
    thread.join(STOP_TIMEOUT_MS)
    return status().also { onStatus?.invoke(it) }
  }

  fun status(): RecorderStatus {
    val state = state
    val stats = stats
    val endNs = if (state == State.RECORDING) SystemClock.elapsedRealtimeNanos() else stopElapsedNs
    return RecorderStatus(
      isRecording = state == State.RECORDING,
      mode = mode,
      csvPath = csvFile?.absolutePath,
      durationSec = if (startElapsedNs == 0L) 0.0 else ((endNs - startElapsedNs) / 1e9).coerceAtLeast(0.0),
      sampleCount = stats.count,
      rateHz = stats.rateHz,
      maxIntervalMs = stats.maxIntervalNs / 1e6,
      error = error,
    )
  }

  override fun onSensorChanged(event: SensorEvent) {
    if (state != State.RECORDING) return
    val timestampNs = event.timestamp
    try {
      writer!!.write(timestampNs, event.values[0], event.values[1], event.values[2])
    } catch (e: IOException) {
      fail(e)
      return
    }
    stats = stats.plus(timestampNs)
  }

  override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) = Unit

  private val tick = object : Runnable {
    override fun run() {
      if (state != State.RECORDING) return
      try {
        writer!!.flush()
      } catch (e: IOException) {
        fail(e)
        return
      }
      onStatus?.invoke(status())
      // Fixed cadence without drift; skip missed ticks instead of bursting.
      nextTickUptimeMs = maxOf(nextTickUptimeMs + STATUS_INTERVAL_MS, SystemClock.uptimeMillis())
      handler!!.postAtTime(this, nextTickUptimeMs)
    }
  }

  @Synchronized
  private fun markStopped(): Boolean {
    if (state != State.RECORDING) return false
    val clock = ClockPair.capture()
    stopClock = clock
    stopElapsedNs = clock.elapsedRealtimeNs
    state = State.STOPPED
    return true
  }

  /** Write failure on the recorder thread: stop recording and keep what was written. */
  private fun fail(e: IOException) {
    if (error == null) error = e.message ?: e.toString()
    if (!markStopped()) return
    sensorManager.unregisterListener(this)
    handler!!.removeCallbacks(tick)
    finish()
    thread!!.quitSafely()
    onStatus?.invoke(status())
  }

  /** Runs on the recorder thread once recording has stopped. */
  private fun finish() {
    try {
      writer!!.close()
    } catch (e: IOException) {
      if (error == null) error = e.message ?: e.toString()
    }
    try {
      metadata!!.writeStop(stopClock!!, status(), stats)
    } catch (e: IOException) {
      if (error == null) error = e.message ?: e.toString()
    }
  }

  companion object {
    private const val STATUS_INTERVAL_MS = 1000L
    private const val STOP_TIMEOUT_MS = 2000L
  }
}
