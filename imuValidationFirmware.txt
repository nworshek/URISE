#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

/*
  IMU Validation Arduino Firmware
  --------------------------------
  Use with the Python IMU validation software.

  Serial commands from Python:
    PING
    STATUS
    STOP
    TEST:STOP
    TEST:START:M1:255:5000
    TEST:START:M1,M3,M5:180:5000

  Serial responses back to Python:
    READY
    ACK:TEST_START
    ACK:TEST_STOP
    STATUS:M1=OFF,M2=ON,M3=OFF,M4=OFF,M5=OFF,M6=OFF
    EVENT:M3:ON
    EVENT:M3:OFF
    IMU:<millis>,<ax>,<ay>,<az>,<gx>,<gy>,<gz>

  Hardware notes:
  - MPU6050 on I2C
  - 6 motors max
  - Motors must be driven through proper drivers/transistors
  - Do not power motors directly from Arduino pins
*/

Adafruit_MPU6050 mpu;

const int MOTOR_COUNT = 6;
const int motorPins[MOTOR_COUNT] = {3, 5, 6, 9, 10, 11};

bool motorSelected[MOTOR_COUNT] = {false, false, false, false, false, false};
bool motorState[MOTOR_COUNT]    = {false, false, false, false, false, false};
int  motorIntensity[MOTOR_COUNT] = {0, 0, 0, 0, 0, 0};

bool testRunning = false;
unsigned long testStartMillis = 0;
unsigned long testDurationMs = 0;
unsigned long lastImuSampleMillis = 0;
const unsigned long imuSampleIntervalMs = 20;   // 50 Hz

String inputBuffer = "";

void setup() {
  Serial.begin(115200);
  Wire.begin();

  for (int i = 0; i < MOTOR_COUNT; i++) {
    pinMode(motorPins[i], OUTPUT);
    analogWrite(motorPins[i], 0);
  }

  if (!mpu.begin()) {
    Serial.println("ERROR:MPU6050 not found");
  } else {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }

  delay(500);
  Serial.println("FIRMWARE_VERSION_2");
  Serial.println("READY");
  sendStatus();
}

void loop() {
  readSerialCommands();
  updateTestState();
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (inputBuffer.length() > 0) {
        processCommand(inputBuffer);
        inputBuffer = "";
      }
    } else {
      inputBuffer += c;
    }
  }
}

void processCommand(String cmd) {
  cmd.trim();

  if (cmd.length() == 0) return;

  if (cmd == "PING") {
    Serial.println("READY");
    return;
  }

  if (cmd == "STATUS") {
    sendStatus();
    return;
  }

  if (cmd == "STOP" || cmd == "TEST:STOP") {
    stopAllMotors();
    clearSelections();
    testRunning = false;
    Serial.println("ACK:TEST_STOP");
    sendStatus();
    return;
  }

  if (cmd.startsWith("TEST:START:")) {
    handleTestStart(cmd);
    return;
  }

  Serial.print("ERROR:Unknown command: ");
  Serial.println(cmd);
}

void handleTestStart(String cmd) {
  // Expected examples:
  // TEST:START:M1:255:5000
  // TEST:START:M1,M3,M5:180:5000

  int p1 = cmd.indexOf(':');               // after TEST
  int p2 = cmd.indexOf(':', p1 + 1);       // after START
  int p3 = cmd.indexOf(':', p2 + 1);       // after motor list
  int p4 = cmd.indexOf(':', p3 + 1);       // after intensity

  if (p1 == -1 || p2 == -1 || p3 == -1 || p4 == -1) {
    Serial.println("ERROR:Bad TEST:START format");
    return;
  }

  String motorList = cmd.substring(p2 + 1, p3);
  String intensityStr = cmd.substring(p3 + 1, p4);
  String durationStr = cmd.substring(p4 + 1);

  motorList.trim();
  intensityStr.trim();
  durationStr.trim();

  int intensity = intensityStr.toInt();
  unsigned long durationMs = durationStr.toInt();

  if (intensity < 0) intensity = 0;
  if (intensity > 255) intensity = 255;

  if (durationMs == 0) {
    Serial.println("ERROR:Duration must be > 0");
    return;
  }

  clearSelections();

  if (!parseMotorSelection(motorList)) {
    Serial.println("ERROR:Invalid motor list");
    return;
  }

  applySelectedMotors(intensity);
  testDurationMs = durationMs;
  testStartMillis = millis();
  lastImuSampleMillis = 0;
  testRunning = true;

  Serial.println("ACK:TEST_START");
  sendStatus();
}

bool parseMotorSelection(String motorList) {
  motorList.trim();
  if (motorList.length() == 0) return false;

  int start = 0;
  while (start < motorList.length()) {
    int commaIndex = motorList.indexOf(',', start);
    String token;

    if (commaIndex == -1) {
      token = motorList.substring(start);
      start = motorList.length();
    } else {
      token = motorList.substring(start, commaIndex);
      start = commaIndex + 1;
    }

    token.trim();
    token.toUpperCase();

    if (token.length() < 2 || token.charAt(0) != 'M') {
      return false;
    }

    int motorNumber = token.substring(1).toInt();
    if (motorNumber < 1 || motorNumber > MOTOR_COUNT) {
      return false;
    }

    motorSelected[motorNumber - 1] = true;
  }

  return true;
}

void clearSelections() {
  for (int i = 0; i < MOTOR_COUNT; i++) {
    motorSelected[i] = false;
  }
}

void applySelectedMotors(int intensity) {
  for (int i = 0; i < MOTOR_COUNT; i++) {
    if (motorSelected[i]) {
      setMotor(i, intensity);
    } else {
      setMotor(i, 0);
    }
  }
}

void setMotor(int index, int pwmValue) {
  if (index < 0 || index >= MOTOR_COUNT) return;

  if (pwmValue < 0) pwmValue = 0;
  if (pwmValue > 255) pwmValue = 255;

  analogWrite(motorPins[index], pwmValue);

  bool newState = (pwmValue > 0);
  motorIntensity[index] = pwmValue;

  if (motorState[index] != newState) {
    motorState[index] = newState;
    Serial.print("EVENT:M");
    Serial.print(index + 1);
    Serial.print(":");
    Serial.println(newState ? "ON" : "OFF");
  }
}

void stopAllMotors() {
  for (int i = 0; i < MOTOR_COUNT; i++) {
    setMotor(i, 0);
  }
}

void updateTestState() {
  if (!testRunning) return;

  unsigned long now = millis();

  if (now - testStartMillis >= testDurationMs) {
    stopAllMotors();
    clearSelections();
    testRunning = false;
    Serial.println("ACK:TEST_STOP");
    sendStatus();
    return;
  }

  if (lastImuSampleMillis == 0 || now - lastImuSampleMillis >= imuSampleIntervalMs) {
    lastImuSampleMillis = now;
    sendImuData();
  }
}

void sendImuData() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  Serial.print("IMU:");
  Serial.print(millis());
  Serial.print(",");
  Serial.print(a.acceleration.x, 4);
  Serial.print(",");
  Serial.print(a.acceleration.y, 4);
  Serial.print(",");
  Serial.print(a.acceleration.z, 4);
  Serial.print(",");
  Serial.print(g.gyro.x, 4);
  Serial.print(",");
  Serial.print(g.gyro.y, 4);
  Serial.print(",");
  Serial.println(g.gyro.z, 4);
}

void sendStatus() {
  Serial.print("STATUS:");
  for (int i = 0; i < MOTOR_COUNT; i++) {
    Serial.print("M");
    Serial.print(i + 1);
    Serial.print("=");
    Serial.print(motorState[i] ? "ON" : "OFF");
    if (i < MOTOR_COUNT - 1) Serial.print(",");
  }
  Serial.println();
}