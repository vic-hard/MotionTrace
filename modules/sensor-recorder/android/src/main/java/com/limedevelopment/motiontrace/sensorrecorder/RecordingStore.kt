package com.limedevelopment.motiontrace.sensorrecorder

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.io.IOException

/** The recordings folder: `<id>.csv` + `<id>.json` pairs written by [SensorRecorder]. */
class RecordingStore(val dir: File) {
  /** Newest first: ids start with the start time. */
  fun list(): List<RecordingInfo> {
    return (dir.listFiles { file -> file.name.endsWith(CSV) } ?: emptyArray())
      .map { info(it.nameWithoutExtension) }
      .sortedByDescending { it.id }
  }

  /** The recording's files that exist. */
  fun files(id: String): List<File> = listOf(file(id, CSV), file(id, JSON)).filter { it.exists() }

  fun delete(id: String) {
    for (file in files(id)) {
      if (!file.delete()) throw IOException("Cannot delete $file")
    }
  }

  private fun info(id: String): RecordingInfo {
    // Missing or unreadable metadata still lists the recording, just without details.
    val metadata = runCatching { JSONObject(file(id, JSON).readText()) }.getOrNull()
    val result = metadata?.optJSONObject("result")
    return RecordingInfo(
      id = id,
      mode = metadata?.optJSONObject("recording")?.optString("mode"),
      startedAtMs = metadata?.optJSONObject("clockAtStart")?.optLong("currentTimeMillis"),
      sizeBytes = files(id).sumOf { it.length() },
      isComplete = result != null,
      durationSec = result?.optDouble("durationSec"),
      sampleCount = result?.optLong("sampleCount"),
      rateHz = result?.optDouble("rateHz"),
    )
  }

  private fun file(id: String, extension: String): File {
    // Ids come from JS: never let one point outside the folder.
    require(ID_PATTERN.matches(id)) { "Invalid recording id '$id'" }
    return File(dir, id + extension)
  }

  companion object {
    private const val CSV = ".csv"
    private const val JSON = ".json"
    private val ID_PATTERN = Regex("[A-Za-z0-9_-]+")

    /** App-specific external storage: no permissions needed, reachable with `adb pull`. */
    fun default(context: Context) =
      RecordingStore(
        File(
          context.getExternalFilesDir(null) ?: context.filesDir, "recordings"
        )
      )
  }
}
