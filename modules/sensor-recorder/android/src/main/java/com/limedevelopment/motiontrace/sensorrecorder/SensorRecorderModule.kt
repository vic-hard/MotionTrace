package com.limedevelopment.motiontrace.sensorrecorder

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class SensorRecorderModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("SensorRecorder")

    Events("onChange")

    Function("hello") {
      "Hello world!"
    }

    AsyncFunction("setValueAsync") { value: String ->
      sendEvent("onChange", mapOf(
        "value" to value
      ))
    }
  }
}
