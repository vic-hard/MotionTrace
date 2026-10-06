import ExpoModulesCore

public class SensorRecorderModule: Module {
  public func definition() -> ModuleDefinition {
    Name("SensorRecorder")

    Events("onChange")

    Function("hello") {
      return "Hello world!"
    }

    AsyncFunction("setValueAsync") { (value: String) in
      self.sendEvent("onChange", [
        "value": value
      ])
    }
  }
}
