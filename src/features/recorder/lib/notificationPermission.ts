import { PermissionsAndroid, Platform } from "react-native";

/**
 * Asks for POST_NOTIFICATIONS (Android 13+) so the recording notification is visible.
 * Recording works without it, so the answer is not checked.
 */
export async function requestNotificationPermission(): Promise<void> {
  if (Platform.OS !== "android" || Platform.Version < 33) return;
  await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS,
  );
}
