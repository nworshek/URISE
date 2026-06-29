#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

const int NUM_MOTORS = 13;

// Active-low motor control:
// 0 = fully ON
// 4095 = fully OFF
const int PCA_OFF = 4095;

void setup() {
  Serial.begin(115200);
  Wire.begin();

  pca.begin();
  pca.setPWMFreq(1000);

  allOff();

  Serial.println("HAPTIC_GLOVE_READY");
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    handleCommand(command);
  }
}

void handleCommand(String command) {
  if (command == "STOP") {
    allOff();
    Serial.println("OK:STOP");
    return;
  }

  if (command.startsWith("ALL:")) {
    int intensity = command.substring(4).toInt();
    setAllMotors(intensity);
    Serial.println("OK:" + command);
    return;
  }

  if (command.startsWith("PATTERN:")) {
    handlePattern(command);
    return;
  }

  if (command.startsWith("M")) {
    int colonIndex = command.indexOf(':');

    if (colonIndex == -1) {
      Serial.println("ERROR:BAD_COMMAND");
      return;
    }

    int motorNumber = command.substring(1, colonIndex).toInt();
    int intensity = command.substring(colonIndex + 1).toInt();

    setMotor(motorNumber, intensity);

    Serial.println("OK:" + command);
    return;
  }

  Serial.println("ERROR:UNKNOWN_COMMAND");
}

void handlePattern(String command) {
  int firstColon = command.indexOf(':');
  int secondColon = command.indexOf(':', firstColon + 1);
  int thirdColon = command.indexOf(':', secondColon + 1);

  if (firstColon == -1 || secondColon == -1 || thirdColon == -1) {
    Serial.println("ERROR:BAD_PATTERN");
    return;
  }

  String pattern = command.substring(firstColon + 1, secondColon);
  int intensity = command.substring(secondColon + 1, thirdColon).toInt();
  int durationMs = command.substring(thirdColon + 1).toInt();

  if (pattern == "SWEEP") {
    sweepPattern(intensity, durationMs);
  } else if (pattern == "ODD") {
    oddPattern(intensity, durationMs);
  } else if (pattern == "EVEN") {
    evenPattern(intensity, durationMs);
  } else {
    Serial.println("ERROR:UNKNOWN_PATTERN");
    return;
  }

  Serial.println("OK:PATTERN:" + pattern);
}

void setMotor(int motorNumber, int intensity) {
  if (motorNumber < 1 || motorNumber > NUM_MOTORS) {
    Serial.println("ERROR:BAD_MOTOR");
    return;
  }

  intensity = constrain(intensity, 0, 255);

  int channel = motorNumber - 1;

  // Active-low mapping:
  // intensity 0   -> PCA 4095 -> OFF
  // intensity 255 -> PCA 0    -> ON
  int pwmValue = map(intensity, 0, 255, 4095, 0);

  pca.setPWM(channel, 0, pwmValue);
}

void setAllMotors(int intensity) {
  for (int motor = 1; motor <= NUM_MOTORS; motor++) {
    setMotor(motor, intensity);
  }
}

void allOff() {
  for (int channel = 0; channel < 16; channel++) {
    pca.setPWM(channel, 0, PCA_OFF);
  }
}

void sweepPattern(int intensity, int durationMs) {
  allOff();

  for (int motor = 1; motor <= NUM_MOTORS; motor++) {
    setMotor(motor, intensity);
    delay(durationMs);
    setMotor(motor, 0);
  }
}

void oddPattern(int intensity, int durationMs) {
  allOff();

  for (int motor = 1; motor <= NUM_MOTORS; motor += 2) {
    setMotor(motor, intensity);
  }

  delay(durationMs);
  allOff();
}

void evenPattern(int intensity, int durationMs) {
  allOff();

  for (int motor = 2; motor <= NUM_MOTORS; motor += 2) {
    setMotor(motor, intensity);
  }

  delay(durationMs);
  allOff();
}