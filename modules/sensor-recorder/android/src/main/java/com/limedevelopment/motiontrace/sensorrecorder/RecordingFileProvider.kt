package com.limedevelopment.motiontrace.sensorrecorder

import androidx.core.content.FileProvider

/**
 * Gives other apps temporary read access to recordings when sharing. A subclass, so its
 * `<provider>` doesn't clash in the merged manifest with other libraries' FileProviders.
 */
class RecordingFileProvider : FileProvider() {
  companion object {
    /** Must match `android:authorities` in the module manifest. */
    fun authority(packageName: String) = "$packageName.sensorrecorder.fileprovider"
  }
}
