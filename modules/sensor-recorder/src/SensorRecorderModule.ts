import { NativeModule, requireNativeModule } from "expo";

import {
  RecorderStatus,
  RecordingMode,
  SensorRecorderModuleEvents,
} from "./SensorRecorder.types";

declare class SensorRecorderModule extends NativeModule<SensorRecorderModuleEvents> {
  start(mode: RecordingMode): Promise<RecorderStatus>;
  stop(): Promise<RecorderStatus>;
  getStatus(): RecorderStatus;
}

export default requireNativeModule<SensorRecorderModule>("SensorRecorder");
