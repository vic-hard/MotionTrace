import { NativeModule, requireNativeModule } from "expo";

import {
  RecorderStatus,
  RecordingInfo,
  RecordingMode,
  SensorRecorderModuleEvents,
} from "./SensorRecorder.types";

declare class SensorRecorderModule extends NativeModule<SensorRecorderModuleEvents> {
  start(mode: RecordingMode): Promise<RecorderStatus>;
  stop(): Promise<RecorderStatus>;
  getStatus(): RecorderStatus;
  /** Newest first, without the recording in progress. */
  listRecordings(): Promise<RecordingInfo[]>;
  /** Opens the system share sheet with the CSV and JSON of each recording. */
  shareRecordings(ids: string[]): Promise<void>;
  deleteRecordings(ids: string[]): Promise<void>;
}

export default requireNativeModule<SensorRecorderModule>("SensorRecorder");
