export type RecordingMode = "100hz" | "max";

export type RecorderStatus = {
  isRecording: boolean;
  mode: RecordingMode | null;
  csvPath: string | null;
  /** Wall time since start, in seconds. */
  durationSec: number;
  sampleCount: number;
  /** Average rate over all samples, from sensor timestamps. */
  rateHz: number;
  /** Largest interval between consecutive samples. */
  maxIntervalMs: number;
  error: string | null;
};

export type SensorRecorderModuleEvents = {
  /** Sent on start, about once per second while recording, and once after stopping. */
  onStatus: (status: RecorderStatus) => void;
};
