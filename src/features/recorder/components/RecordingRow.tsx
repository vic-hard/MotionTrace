import { Pressable, StyleSheet, Text, View } from "react-native";

import { RecordingInfo } from "@modules/sensor-recorder";

import {
  formatDateTime,
  formatDuration,
  formatSize,
  MODE_LABELS,
} from "../lib/format";

type Props = {
  recording: RecordingInfo;
  onShare: () => void;
  onDelete: () => void;
};

export function RecordingRow({ recording, onShare, onDelete }: Props) {
  const r = recording;
  const title = [
    r.startedAtMs !== null ? formatDateTime(r.startedAtMs) : r.id,
    r.mode && MODE_LABELS[r.mode],
  ]
    .filter(Boolean)
    .join(" · ");
  const details = r.isComplete
    ? [
        formatDuration(r.durationSec ?? 0),
        `${r.sampleCount} samples`,
        `${(r.rateHz ?? 0).toFixed(1)} Hz`,
        formatSize(r.sizeBytes),
      ]
    : ["Interrupted", formatSize(r.sizeBytes)];

  return (
    <View style={styles.row}>
      <View style={styles.info}>
        <Text style={styles.title}>{title}</Text>
        <Text style={[styles.details, !r.isComplete && styles.interrupted]}>
          {details.join(" · ")}
        </Text>
      </View>
      <Pressable onPress={onShare} hitSlop={8}>
        <Text style={styles.action}>Share</Text>
      </Pressable>
      <Pressable onPress={onDelete} hitSlop={8}>
        <Text style={[styles.action, styles.delete]}>Delete</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#d1d5db",
  },
  info: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontSize: 15,
    fontWeight: "500",
  },
  details: {
    color: "#6b7280",
    fontSize: 13,
  },
  interrupted: {
    color: "#b45309",
  },
  action: {
    color: "#2563eb",
    fontWeight: "500",
  },
  delete: {
    color: "#dc2626",
  },
});
