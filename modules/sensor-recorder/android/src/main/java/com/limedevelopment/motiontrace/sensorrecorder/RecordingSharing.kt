package com.limedevelopment.motiontrace.sensorrecorder

import android.content.ClipData
import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import java.io.File

object RecordingSharing {
  /** The system share sheet for [files], sent together in one action. */
  fun chooserIntent(context: Context, files: List<File>): Intent {
    require(files.isNotEmpty()) { "Nothing to share" }
    val authority = RecordingFileProvider.authority(context.packageName)
    val uris = ArrayList(files.map { FileProvider.getUriForFile(context, authority, it) })
    val send = Intent(Intent.ACTION_SEND_MULTIPLE).apply {
      type = "*/*" // CSV and JSON together
      putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
      // The read grant travels with ClipData, through the chooser to the target app.
      clipData = ClipData.newRawUri(null, uris.first()).apply {
        uris.drop(1).forEach { addItem(ClipData.Item(it)) }
      }
      addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    return Intent.createChooser(send, null)
  }
}
