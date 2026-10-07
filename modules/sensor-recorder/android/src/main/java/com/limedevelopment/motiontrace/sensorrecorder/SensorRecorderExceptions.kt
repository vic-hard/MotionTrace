package com.limedevelopment.motiontrace.sensorrecorder

import expo.modules.kotlin.exception.CodedException

// Codes are inferred from class names: ERR_INVALID_MODE, ERR_ALREADY_RECORDING,
// ERR_RECORDING_IN_PROGRESS.

class InvalidModeException(mode: String) :
  CodedException("Unknown recording mode '$mode', expected one of ${RecordingMode.entries.map { it.id }}")

class AlreadyRecordingException : CodedException("A recording is already in progress")

class RecordingInProgressException : CodedException("The recording is still in progress")
