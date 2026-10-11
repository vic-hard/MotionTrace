package com.limedevelopment.motiontrace.sensorrecorder

import android.annotation.SuppressLint
import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import java.util.concurrent.CopyOnWriteArraySet

/**
 * Foreground service (type `health`) holding a partial wake lock, so a recording keeps going with
 * the screen off. It runs exactly as long as the recording: [start] starts it, and it stops itself
 * once the recording stops, whatever the reason (stop command, notification action, write error).
 *
 * The companion owns the process's recording, so it outlives the Activity and JS reloads.
 * No Expo dependencies.
 */
class RecorderService : Service() {
  private var wakeLock: PowerManager.WakeLock? = null

  /** The recording this instance went foreground for. */
  private var foregroundFor: SensorRecorder? = null

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onCreate() {
    super.onCreate()
    instance = this
    // Gravity is a non-wakeup sensor: once the CPU sleeps, its events overflow the FIFO and are lost.
    wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
      .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, WAKE_LOCK_TAG)
      .apply {
        setReferenceCounted(false)
        acquire()
      }
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    if (intent?.action == ACTION_STOP) {
      stop()
    } else {
      goForeground()
    }
    stopIfIdle()
    // After a process kill there is no recording left to resume.
    return START_NOT_STICKY
  }

  override fun onDestroy() {
    // Normally the recording has already stopped. If the system stops the service first, close the files.
    foregroundFor?.stop("The foreground service was stopped")
    wakeLock?.release()
    if (instance === this) instance = null
    super.onDestroy()
  }

  /**
   * Required after startForegroundService(), even if the recording has already stopped.
   *
   * FOREGROUND_SERVICE_TYPE_HEALTH (API 34) is an inlined int, and ServiceCompat drops types the
   * platform doesn't know: before Android 14 the service just starts without a type.
   */
  @SuppressLint("InlinedApi")
  private fun goForeground() {
    val current = recorder
    try {
      ServiceCompat.startForeground(
        this,
        NOTIFICATION_ID,
        notification(current?.mode),
        ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH,
      )
      foregroundFor = current
    } catch (e: Exception) {
      // E.g. refused in the background on Android 12+. Without it the recording stalls with the screen.
      current?.stop("Cannot start the foreground service: $e")
    }
  }

  private fun stopIfIdle() {
    if (recorder?.isRecording != true) stopSelf()
  }

  private fun notification(mode: RecordingMode?): Notification {
    NotificationManagerCompat.from(this).createNotificationChannel(
      NotificationChannelCompat.Builder(CHANNEL_ID, NotificationManagerCompat.IMPORTANCE_LOW)
        .setName("Recording")
        .build()
    )
    val startedAtMs = System.currentTimeMillis() - (status().durationSec * 1000).toLong()
    val stopIntent = PendingIntent.getService(
      this,
      0,
      Intent(this, RecorderService::class.java).setAction(ACTION_STOP),
      PendingIntent.FLAG_IMMUTABLE,
    )
    val openIntent = packageManager.getLaunchIntentForPackage(packageName)?.let {
      PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE)
    }
    return NotificationCompat.Builder(this, CHANNEL_ID)
      .setSmallIcon(R.drawable.sensor_recorder_notification)
      .setContentTitle("Recording gravity")
      .setContentText(
        when (mode) {
          RecordingMode.HZ_100 -> "100 Hz"
          RecordingMode.MAX -> "Max rate"
          null -> null
        }
      )
      .setWhen(startedAtMs)
      .setShowWhen(true)
      .setUsesChronometer(true)
      .setOngoing(true)
      .setCategory(NotificationCompat.CATEGORY_SERVICE)
      .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
      .setContentIntent(openIntent)
      .addAction(0, "Stop", stopIntent)
      .build()
  }

  companion object {
    private const val CHANNEL_ID = "sensor_recorder"
    private const val NOTIFICATION_ID = 1
    private const val ACTION_STOP = "com.limedevelopment.motiontrace.sensorrecorder.STOP"
    private const val WAKE_LOCK_TAG = "MotionTrace:SensorRecorder"

    /** The latest recording; kept after it stops, so its final status and error stay readable. */
    @Volatile private var recorder: SensorRecorder? = null

    /** Main thread only. */
    private var instance: RecorderService? = null

    private val listeners = CopyOnWriteArraySet<(RecorderStatus) -> Unit>()
    private val mainHandler = Handler(Looper.getMainLooper())

    val isRecording get() = recorder?.isRecording == true

    fun status(): RecorderStatus = recorder?.status() ?: RecorderStatus.IDLE

    /** Called on start, every second while recording (on the recorder thread) and once after stopping. */
    fun addStatusListener(listener: (RecorderStatus) -> Unit) {
      listeners.add(listener)
    }

    fun removeStatusListener(listener: (RecorderStatus) -> Unit) {
      listeners.remove(listener)
    }

    /** Starts a recording and the service around it. Throws if the recording can't be started. */
    @Synchronized
    fun start(context: Context, mode: RecordingMode): RecorderStatus {
      check(!isRecording) { "A recording is already in progress" }
      val app = context.applicationContext
      val newRecorder = SensorRecorder(app, mode, RecordingStore.default(app).dir, ::onStatus)
      // Kept before start(): stop() reaches it whatever start() throws, and a failed start
      // leaves its error in status().
      recorder = newRecorder
      newRecorder.start()
      try {
        ContextCompat.startForegroundService(app, Intent(app, RecorderService::class.java))
      } catch (e: Exception) {
        newRecorder.stop("Cannot start the foreground service: $e")
        throw e
      }
      return newRecorder.status()
    }

    /** Stops the recording; files are closed on return. The service then stops itself. */
    fun stop(): RecorderStatus = recorder?.stop() ?: RecorderStatus.IDLE

    private fun onStatus(status: RecorderStatus) {
      listeners.forEach { it(status) }
      if (!status.isRecording) mainHandler.post { instance?.stopIfIdle() }
    }
  }
}
