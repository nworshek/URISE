#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

const int NUM_MOTORS = 16;
const int MAX_PWM = 4095;
const bool ACTIVE_LOW = true;

void setMotor(int motor, int intensity) {
  if (motor < 0 || motor >= NUM_MOTORS) return;

  intensity = constrain(intensity, 0, 255);
  int pwmValue = map(intensity, 0, 255, 0, MAX_PWM);

  if (ACTIVE_LOW) {
    pwmValue = MAX_PWM - pwmValue;
  }

  pca.setPWM(motor, 0, pwmValue);
}

void allOff() {
  for (int i = 0; i < NUM_MOTORS; i++) {
    setMotor(i, 0);
  }
}

void allOn(int intensity) {
  for (int i = 0; i < NUM_MOTORS; i++) {
    setMotor(i, intensity);
  }
}

void runPattern(String pattern, int intensity, int durationMs) {
  allOff();

  if (pattern == "ALL") {
    allOn(intensity);
    delay(durationMs);
  } else if (pattern == "ODD") {
    for (int i = 0; i < NUM_MOTORS; i += 2) setMotor(i, intensity);
    delay(durationMs);
  } else if (pattern == "EVEN") {
    for (int i = 1; i < NUM_MOTORS; i += 2) setMotor(i, intensity);
    delay(durationMs);
  } else if (pattern == "FIRST_HALF") {
    for (int i = 0; i < 8; i++) setMotor(i, intensity);
    delay(durationMs);
  } else if (pattern == "SECOND_HALF") {
    for (int i = 8; i < 16; i++) setMotor(i, intensity);
    delay(durationMs);
  } else if (pattern == "SWEEP") {
    int stepDelay = durationMs / NUM_MOTORS;
    if (stepDelay < 50) stepDelay = 50;

    for (int i = 0; i < NUM_MOTORS; i++) {
      allOff();
      setMotor(i, intensity);
      delay(stepDelay);
    }
  }

  allOff();
}

void handleCommand(String cmd) {
  cmd.trim();

  if (cmd == "PING") {
    Serial.println("PONG:NANO_PCA9685");
    return;
  }

  if (cmd == "STOP" || cmd == "ALL_OFF") {
    allOff();
    Serial.println("OK:ALL_OFF");
    return;
  }

  if (cmd.startsWith("MOTOR:")) {
    int p1 = cmd.indexOf(':');
    int p2 = cmd.indexOf(':', p1 + 1);
    int p3 = cmd.indexOf(':', p2 + 1);

    int motor = cmd.substring(p1 + 1, p2).toInt();
    int intensity = cmd.substring(p2 + 1, p3).toInt();
    int durationMs = cmd.substring(p3 + 1).toInt();

    setMotor(motor, intensity);
    Serial.println("OK:MOTOR_ON");
    delay(durationMs);
    setMotor(motor, 0);
    Serial.println("OK:MOTOR_OFF");
    return;
  }

  if (cmd.startsWith("PATTERN:")) {
    int p1 = cmd.indexOf(':');
    int p2 = cmd.indexOf(':', p1 + 1);
    int p3 = cmd.indexOf(':', p2 + 1);

    String pattern = cmd.substring(p1 + 1, p2);
    int intensity = cmd.substring(p2 + 1, p3).toInt();
    int durationMs = cmd.substring(p3 + 1).toInt();

    runPattern(pattern, intensity, durationMs);
    Serial.println("OK:PATTERN_DONE");
    return;
  }

  Serial.println("ERR:UNKNOWN_COMMAND");
}

void setup() {
  Serial.begin(115200);
  Wire.begin(); // Nano uses A4 SDA, A5 SCL

  pca.begin();
  pca.setPWMFreq(1000);

  allOff();

  Serial.println("READY:NANO_PCA9685_16_MOTOR_VALIDATOR");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    handleCommand(cmd);
  }
}