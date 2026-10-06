import { StyleSheet, Text, View } from 'react-native';

// Recording screen: Start/Stop, status and file export land here.
export default function RecorderScreen() {
  return (
    <View style={styles.container}>
      <Text>MotionTrace</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
