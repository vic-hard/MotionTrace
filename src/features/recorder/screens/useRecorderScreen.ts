import { useEvent } from "expo";
import { useEffect, useState } from "react";

import SensorRecorder, {
  RecordingInfo,
  RecordingMode,
} from "@modules/sensor-recorder";

const toMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function useRecorderScreen() {
  const status = useEvent(
    SensorRecorder,
    "onStatus",
    SensorRecorder.getStatus(),
  );
  const [mode, setMode] = useState<RecordingMode>("100hz");
  const [recordings, setRecordings] = useState<RecordingInfo[]>([]);
  const [commandError, setCommandError] = useState<string | null>(null);

  // On open, and whenever recording starts or stops: a recording joins the list once it stops.
  useEffect(() => {
    SensorRecorder.listRecordings()
      .then(setRecordings)
      .catch((e: unknown) => setCommandError(toMessage(e)));
  }, [status.isRecording]);

  const run = (command: () => Promise<unknown>) => {
    setCommandError(null);
    command().catch((e: unknown) => setCommandError(toMessage(e)));
  };

  return {
    status,
    mode,
    setMode,
    recordings,
    // A failed command, or a write error reported by the recorder.
    error: commandError ?? status.error,
    start: () => run(() => SensorRecorder.start(mode)),
    stop: () => run(() => SensorRecorder.stop()),
    share: (id: string) => run(() => SensorRecorder.shareRecordings([id])),
    remove: (id: string) =>
      run(async () => {
        await SensorRecorder.deleteRecordings([id]);
        setRecordings(await SensorRecorder.listRecordings());
      }),
  };
}
