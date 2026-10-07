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

export type RecordingInfo = {
  /** File name without extension, shared by the CSV and the JSON. */
  id: string;
  mode: RecordingMode | null;
  startedAtMs: number | null;
  /** CSV + JSON. */
  sizeBytes: number;
  /** False if the recording was cut off (its metadata has no result). */
  isComplete: boolean;
  // Only for complete recordings.
  durationSec: number | null;
  sampleCount: number | null;
  rateHz: number | null;
};

export type SensorRecorderModuleEvents = {
  /** Sent on start, about once per second while recording, and once after stopping. */
  onStatus: (status: RecorderStatus) => void;
};
