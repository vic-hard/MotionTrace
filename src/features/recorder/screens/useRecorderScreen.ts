import { useEvent } from "expo";
import { useState } from "react";

import SensorRecorder, { RecordingMode } from "@modules/sensor-recorder";

export function useRecorderScreen() {
  const status = useEvent(
    SensorRecorder,
    "onStatus",
    SensorRecorder.getStatus(),
  );
  const [commandError, setCommandError] = useState<string | null>(null);

  const run = (command: () => Promise<unknown>) => {
    setCommandError(null);
    command().catch((e: unknown) =>
      setCommandError(e instanceof Error ? e.message : String(e)),
    );
  };

  return {
    status,
    // A failed start/stop call, or a write error reported by the recorder.
    error: commandError ?? status.error,
    start: (mode: RecordingMode) => run(() => SensorRecorder.start(mode)),
    stop: () => run(() => SensorRecorder.stop()),
  };
}
