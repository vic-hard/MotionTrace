import ExpoModulesCore

// iOS is out of scope for the prototype; this stub only keeps the JS API shape.
public class SensorRecorderModule: Module {
  public func definition() -> ModuleDefinition {
    Name("SensorRecorder")

    Events("onStatus")

    AsyncFunction("start") { (mode: String) in
      throw Exception(name: "NotSupported", description: "Recording is not implemented on iOS", code: "ERR_NOT_SUPPORTED")
    }

    AsyncFunction("stop") {
      return SensorRecorderModule.idleStatus
    }

    Function("getStatus") {
      return SensorRecorderModule.idleStatus
    }
  }

  private static let idleStatus: [String: Any?] = [
    "isRecording": false,
    "mode": nil,
    "csvPath": nil,
    "durationSec": 0,
    "sampleCount": 0,
    "rateHz": 0,
    "maxIntervalMs": 0,
    "error": nil,
  ]
}
