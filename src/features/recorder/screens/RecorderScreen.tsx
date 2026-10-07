import { Button, StyleSheet, Text, View } from "react-native";

import { useRecorderScreen } from "./useRecorderScreen";

// Bare-bones controls for checking native recording (stage 3); the real screen comes in stage 5.
export default function RecorderScreen() {
  const { status, error, start, stop } = useRecorderScreen();

  return (
    <View style={styles.container}>
      <View style={styles.buttons}>
        <Button
          title="Start 100 Hz"
          disabled={status.isRecording}
          onPress={() => start("100hz")}
        />
        <Button
          title="Start max"
          disabled={status.isRecording}
          onPress={() => start("max")}
        />
        <Button title="Stop" disabled={!status.isRecording} onPress={stop} />
      </View>
      <Text>
        {status.isRecording ? `Recording (${status.mode})` : "Stopped"}
      </Text>
      <Text>Duration: {status.durationSec.toFixed(0)} s</Text>
      <Text>Samples: {status.sampleCount}</Text>
      <Text>Rate: {status.rateHz.toFixed(1)} Hz</Text>
      <Text>Max interval: {status.maxIntervalMs.toFixed(1)} ms</Text>
      {status.csvPath && <Text style={styles.path}>{status.csvPath}</Text>}
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#fff",
    padding: 16,
    gap: 8,
  },
  buttons: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 8,
  },
  path: {
    color: "#666",
    fontSize: 12,
  },
  error: {
    color: "#c00",
  },
});
