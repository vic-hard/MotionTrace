import { NativeModule, requireNativeModule } from 'expo';

import { SensorRecorderModuleEvents } from './SensorRecorder.types';

declare class SensorRecorderModule extends NativeModule<SensorRecorderModuleEvents> {
  hello(): string;
  setValueAsync(value: string): Promise<void>;
}

export default requireNativeModule<SensorRecorderModule>('SensorRecorder');
