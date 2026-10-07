import { useKeepAwake } from "expo-keep-awake";
import {
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { RecordingMode } from "@modules/sensor-recorder";

import { RecordingRow } from "../components/RecordingRow";
import { formatDuration, MODE_LABELS } from "../lib/format";
import { useRecorderScreen } from "./useRecorderScreen";

const MODES: RecordingMode[] = ["100hz", "max"];
const CONTENT_PADDING = 16;

// Rendered only while recording: in M1 recording needs the screen on.
function KeepAwake() {
  useKeepAwake();
  return null;
}

export default function RecorderScreen() {
  const {
    status,
    mode,
    setMode,
    recordings,
    error,
    start,
    stop,
    share,
    remove,
  } = useRecorderScreen();
  const insets = useSafeAreaInsets();
  const recording = status.isRecording;

  const confirmDelete = (id: string) =>
    Alert.alert(
      "Delete recording?",
      "The CSV and JSON files will be removed.",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Delete", style: "destructive", onPress: () => remove(id) },
      ],
    );

  const header = (
    <View style={styles.header}>
      <View style={styles.modes}>
        {MODES.map((m) => (
          <Pressable
            key={m}
            disabled={recording}
            onPress={() => setMode(m)}
            style={[
              styles.mode,
              m === mode && styles.modeSelected,
              recording && styles.disabled,
            ]}
          >
            <Text
              style={[styles.modeText, m === mode && styles.modeTextSelected]}
            >
              {MODE_LABELS[m]}
            </Text>
          </Pressable>
        ))}
      </View>

      <Pressable
        onPress={recording ? stop : start}
        style={[styles.button, recording && styles.buttonStop]}
      >
        <Text style={styles.buttonText}>{recording ? "Stop" : "Start"}</Text>
      </Pressable>

      <View style={styles.status}>
        <Text style={styles.statusTitle}>
          {recording
            ? `Recording · ${status.mode && MODE_LABELS[status.mode]}`
            : "Not recording"}
        </Text>
        <Stat label="Duration" value={formatDuration(status.durationSec)} />
        <Stat label="Samples" value={String(status.sampleCount)} />
        <Stat label="Rate" value={`${status.rateHz.toFixed(1)} Hz`} />
        <Stat
          label="Max interval"
          value={`${status.maxIntervalMs.toFixed(1)} ms`}
        />
      </View>

      {error && <Text style={styles.error}>{error}</Text>}

      <Text style={styles.sectionTitle}>Recordings</Text>
    </View>
  );

  return (
    <>
      {recording && <KeepAwake />}
      <FlatList
        style={styles.screen}
        // Edge-to-edge: keep the last row clear of the system navigation bar.
        contentContainerStyle={[
          styles.content,
          { paddingBottom: CONTENT_PADDING + insets.bottom },
        ]}
        data={recordings}
        keyExtractor={(r) => r.id}
        ListHeaderComponent={header}
        ListEmptyComponent={<Text style={styles.empty}>No recordings yet</Text>}
        renderItem={({ item }) => (
          <RecordingRow
            recording={item}
            onShare={() => share(item.id)}
            onDelete={() => confirmDelete(item.id)}
          />
        )}
      />
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#fff",
  },
  content: {
    padding: CONTENT_PADDING,
  },
  header: {
    gap: 16,
  },
  modes: {
    flexDirection: "row",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#2563eb",
    overflow: "hidden",
  },
  mode: {
    flex: 1,
    paddingVertical: 10,
    alignItems: "center",
  },
  modeSelected: {
    backgroundColor: "#2563eb",
  },
  modeText: {
    color: "#2563eb",
    fontWeight: "500",
  },
  modeTextSelected: {
    color: "#fff",
  },
  disabled: {
    opacity: 0.5,
  },
  button: {
    backgroundColor: "#2563eb",
    borderRadius: 8,
    paddingVertical: 16,
    alignItems: "center",
  },
  buttonStop: {
    backgroundColor: "#dc2626",
  },
  buttonText: {
    color: "#fff",
    fontSize: 18,
    fontWeight: "600",
  },
  status: {
    gap: 6,
  },
  statusTitle: {
    fontSize: 16,
    fontWeight: "600",
  },
  stat: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  statLabel: {
    color: "#6b7280",
  },
  statValue: {
    fontVariant: ["tabular-nums"],
  },
  error: {
    color: "#dc2626",
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "600",
    marginTop: 8,
  },
  empty: {
    color: "#6b7280",
    paddingVertical: 12,
  },
});
