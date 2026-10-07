# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md
@docs/PLAN.md

## Project context

MotionTrace is a technical prototype: verify that Android can reliably record the **Gravity** sensor with the screen off, at quality comparable to the Sensor Logger app (real rate, gaps, timestamps, per-device behavior). Scope is Android only, one sensor, background recording, minimal UI, plus a Python analysis script. iOS, other sensors, microphone and charts are out of scope.

`docs/PLAN.md` (in Russian) is the source of truth for stage status, the CSV/metadata format, and design decisions — read it before starting a stage and update its status table when a stage is done.

## Commands

This is an npm project (`package-lock.json`), so use `npx`.

```bash
npm run android        # expo run:android — build & install the dev client (needed after any native change)
npm start              # Metro only, for JS changes on an already-installed dev client
npx tsc --noEmit
npm run lint           # expo lint src modules (ESLint + Prettier via eslint-plugin-prettier); add `-- --fix` to autofix
npx expo-doctor
# Standalone APK (no Metro), debug-signed: android/app/build/outputs/apk/release/app-release.apk
# arm64-v8a only: building all four ABIs runs the C++ compiler out of memory on this machine
cd android && ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a
```

There is no test suite. Verification is done by building and running on a physical Android phone (sensor behavior can't be checked in an emulator).

## Architecture

- **All recording happens in native code.** JS only sends commands (start / stop / getStatus) and receives a status event about once per second. Raw sensor samples never cross the bridge.
- **Local Expo module `modules/sensor-recorder`** (autolinked via `expo-module.config.json`, module name `SensorRecorder`, Kotlin package `com.limedevelopment.motiontrace.sensorrecorder`). JS entry is `modules/sensor-recorder/index.ts` (API: `start(mode)`, `stop()`, `getStatus()`, event `onStatus`). The Swift side is a stub with the same API, for the future only.
- **Recording classes must stay Expo-independent**: everything in the Kotlin package except `SensorRecorderModule.kt` (a thin wrapper) and `SensorRecorderExceptions.kt` (`CodedException`s for JS) — `SensorRecorder`, `CsvWriter`, `MetadataWriter`, `RecordingMode`, `RecorderStatus`, `SampleStats`, `ClockPair`, `RecordingStore`, `RecordingInfo`, `RecordingSharing`, `RecordingFileProvider`, and the planned `RecorderService`. One class/enum per file. This lets the classes move unchanged into a fully native app if the client chooses that.
- Use only platform SDK sensor APIs (`SensorManager`) — no third-party sensor libraries.
- Android permissions (`FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_HEALTH`, `HIGH_SAMPLING_RATE_SENSORS`, `WAKE_LOCK`, `POST_NOTIFICATIONS`) and the future foreground service are declared in the **module's** `android/src/main/AndroidManifest.xml`, which merges into the app manifest at build time. Foreground service type is `health`.
- Single screen. Routes in `src/app/` only re-export screens (`src/app/index.tsx` → `src/features/recorder/screens/RecorderScreen.tsx`); each screen keeps its state in a sibling hook (`useRecorderScreen.ts`). Aliases: `@/*` → `src/*`, `@modules/*` → `modules/*`.

## Project-specific rules

- Don't do long work inside an Expo `AsyncFunction`: all `AsyncFunction`s across all Expo modules share one background thread. Sensor listening runs on its own `HandlerThread`.
- `SensorEvent.timestamp` is always written to CSV unmodified (`sensor_timestamp_ns`); UTC time is derived from an offset captured at recording start.
- `react-native-gesture-handler` (2.32) and `react-dom` (19.2.3) are pinned for SDK 57 — don't bump them. gesture-handler 3.x breaks the Windows build (260-char path limit), and a mismatched `react-dom` conflicts with `react`.
- To edit/debug Kotlin with IDE support, open the generated `android/` folder in Android Studio (but never commit or hand-edit `android/`).
