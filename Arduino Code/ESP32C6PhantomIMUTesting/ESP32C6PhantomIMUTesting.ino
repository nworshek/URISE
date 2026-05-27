/*
  ESP32-C6 Phantom IMU Validation Firmware
  Hardware target:
    - ESP32-C6-WROOM-1 based board
    - SparkFun Micro 6DoF IMU Breakout BMI270
    - AR/VR 9DOF AHRS module, commonly BNO080/BNO085 style
    - 4 motor driver outputs for haptic belt / phantom testing

  Serial protocol kept compatible with your Python validation software:
    PING
    STATUS
    STOP
    TEST:STOP
    TEST:START:M1:180:5000
    TEST:START:M1,M3,M4:180:5000

  Main Python-compatible IMU output:
    IMU:<millis>,<ax>,<ay>,<az>,<gx>,<gy>,<gz>

  Optional secondary AHRS output:
    AHRS:<millis>,<ax>,<ay>,<az>,<gx>,<gy>,<gz>,<qw>,<qx>,<qy>,<qz>,<accuracy>

  Required Arduino libraries:
    - SparkFun BMI270 Arduino Library
    - Adafruit BNO08x
    - Adafruit BusIO

  Important wiring notes:
    - ESP32-C6 logic is 3.3V. Do not feed 5V logic into the sensors.
    - Motors must be driven through MOSFETs / motor drivers, not directly from ESP32 pins.
    - Update SDA_PIN, SCL_PIN, and motorPins[] to match your actual board wiring.
*/

#include <Wire.h>
#include <math.h>
#include "SparkFun_BMI270_Arduino_Library.h"
#include <Adafruit_BNO08x.h>

// ---------------- User Settings ----------------

// Change these pins to match your ESP32-C6 board wiring.
// ESP32 boards allow custom I2C pins through Wire.begin(SDA, SCL).
#define SDA_PIN 6
#define SCL_PIN 7

// Enable / disable sensors depending on what is physically connected.
#define USE_BMI270 true
#define USE_BNO08X true

// Select which sensor is sent using the Python-compatible IMU: line.
// 1 = BMI270, 2 = BNO08x / BNO080 / BNO085
#define PRIMARY_IMU 1

// If true, BNO08x data is also printed as AHRS: lines.
// Your current Python logger will ignore these unless you update it to parse AHRS lines.
#define OUTPUT_AHRS_LINE true

// BMI270 I2C address. SparkFun default is 0x68. Alternate is 0x69.
uint8_t BMI270_ADDR = BMI2_I2C_PRIM_ADDR; // 0x68
// uint8_t BMI270_ADDR = BMI2_I2C_SEC_ADDR; // 0x69

// BNO08x I2C address. Most BNO080/BNO085 breakout boards use 0x4A or 0x4B.
#define BNO08X_ADDR 0x4A

// IMU sample interval.
// 250 ms gives about 20 samples during a 5000 ms test.
const unsigned long imuSampleIntervalMs = 250;

// Motor settings.
const int MOTOR_COUNT = 4;

// Change these pins to match your motor driver input pins.
// These are example ESP32-C6 GPIOs, not universal requirements.
const int motorPins[MOTOR_COUNT] = {10, 11, 12, 13};

// PWM settings for ESP32 motor control.
const int pwmFreq = 20000;      // 20 kHz PWM, above audible range for many motors/drivers
const int pwmResolution = 8;    // 8-bit range: 0-255

// ---------------- Sensor Objects ----------------

BMI270 bmi270;
Adafruit_BNO08x bno08x(-1); // -1 means no reset pin is used
sh2_SensorValue_t bnoValue;

bool bmi270Ready = false;
bool bno08xReady = false;

// Last BNO08x values. These update whenever the sensor event arrives.
float bno_ax = 0.0;
float bno_ay = 0.0;
float bno_az = 0.0;
float bno_gx = 0.0;
float bno_gy = 0.0;
float bno_gz = 0.0;
float bno_qw = 1.0;
float bno_qx = 0.0;
float bno_qy = 0.0;
float bno_qz = 0.0;
float bno_accuracy = 0.0;

// ---------------- Test State ----------------

bool motorSelected[MOTOR_COUNT] = {false, false, false, false};
bool motorState[MOTOR_COUNT]    = {false, false, false, false};
int  motorIntensity[MOTOR_COUNT] = {0, 0, 0, 0};

bool testRunning = false;
unsigned long testStartMillis = 0;
unsigned long testDurationMs = 0;
unsigned long lastImuSampleMillis = 0;

String inputBuffer = "";

// ---------------- Setup ----------------

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("FIRMWARE_VERSION_ESP32C6_PHANTOM_IMU_1");

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000); // 400 kHz I2C, supported by many IMU boards

  setupMotors();
  setupSensors();

  Serial.println("READY");
  sendStatus();
}

void loop() {
  readSerialCommands();
  updateBNO08xEvents();
  updateTestState();
}

// ---------------- Motor Setup / Control ----------------

void setupMotors() {
  for (int i = 0; i < MOTOR_COUNT; i++) {
    pinMode(motorPins[i], OUTPUT);

#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcAttach(motorPins[i], pwmFreq, pwmResolution);
    ledcWrite(motorPins[i], 0);
#else
    ledcSetup(i, pwmFreq, pwmResolution);
    ledcAttachPin(motorPins[i], i);
    ledcWrite(i, 0);
#endif
  }
}

void writeMotorPWM(int index, int pwmValue) {
  if (index < 0 || index >= MOTOR_COUNT) return;

  if (pwmValue < 0) pwmValue = 0;
  if (pwmValue > 255) pwmValue = 255;

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(motorPins[index], pwmValue);
#else
  ledcWrite(index, pwmValue);
#endif
}

void setMotor(int index, int pwmValue) {
  if (index < 0 || index >= MOTOR_COUNT) return;

  if (pwmValue < 0) pwmValue = 0;
  if (pwmValue > 255) pwmValue = 255;

  writeMotorPWM(index, pwmValue);

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

// ---------------- Sensor Setup ----------------

void setupSensors() {
#if USE_BMI270
  Serial.println("[SETUP] Checking BMI270...");
  if (bmi270.beginI2C(BMI270_ADDR) == BMI2_OK) {
    bmi270Ready = true;
    Serial.println("[SETUP] BMI270 connected");
  } else {
    bmi270Ready = false;
    Serial.println("ERROR:BMI270 not found");
  }
#endif

#if USE_BNO08X
  Serial.println("[SETUP] Checking BNO08x/BNO080/BNO085...");
  if (bno08x.begin_I2C(BNO08X_ADDR, &Wire)) {
    bno08xReady = true;
    Serial.println("[SETUP] BNO08x connected");

    // Report intervals are in microseconds.
    // 20000 us = 50 Hz internal reports. Main serial output is still controlled by imuSampleIntervalMs.
    bno08x.enableReport(SH2_ACCELEROMETER, 20000);
    bno08x.enableReport(SH2_GYROSCOPE_CALIBRATED, 20000);
    bno08x.enableReport(SH2_ROTATION_VECTOR, 20000);
  } else {
    bno08xReady = false;
    Serial.println("ERROR:BNO08x not found");
  }
#endif
}

void updateBNO08xEvents() {
#if USE_BNO08X
  if (!bno08xReady) return;

  while (bno08x.getSensorEvent(&bnoValue)) {
    switch (bnoValue.sensorId) {
      case SH2_ACCELEROMETER:
        bno_ax = bnoValue.un.accelerometer.x;
        bno_ay = bnoValue.un.accelerometer.y;
        bno_az = bnoValue.un.accelerometer.z;
        break;

      case SH2_GYROSCOPE_CALIBRATED:
        bno_gx = bnoValue.un.gyroscope.x;
        bno_gy = bnoValue.un.gyroscope.y;
        bno_gz = bnoValue.un.gyroscope.z;
        break;

      case SH2_ROTATION_VECTOR:
        bno_qw = bnoValue.un.rotationVector.real;
        bno_qx = bnoValue.un.rotationVector.i;
        bno_qy = bnoValue.un.rotationVector.j;
        bno_qz = bnoValue.un.rotationVector.k;
        bno_accuracy = bnoValue.un.rotationVector.accuracy;
        break;
    }

  }
#endif
}

// ---------------- Serial Command Handling ----------------

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

  if (cmd == "SCAN") {
    scanI2C();
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
  // TEST:START:M1:180:5000
  // TEST:START:M1,M3,M4:180:5000

  int p1 = cmd.indexOf(':');
  int p2 = cmd.indexOf(':', p1 + 1);
  int p3 = cmd.indexOf(':', p2 + 1);
  int p4 = cmd.indexOf(':', p3 + 1);

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

// ---------------- Test Timing / IMU Output ----------------

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
    sendPrimaryImuData();

#if OUTPUT_AHRS_LINE
    sendAhrsData();
#endif
  }
}

void sendPrimaryImuData() {
#if PRIMARY_IMU == 1
  sendBMI270AsIMU();
#else
  sendBNO08xAsIMU();
#endif
}

void sendBMI270AsIMU() {
#if USE_BMI270
  if (!bmi270Ready) return;

  bmi270.getSensorData();

  // SparkFun BMI270 library outputs acceleration in g and gyro in deg/sec.
  // Convert acceleration to m/s^2 so it matches your previous MPU6050 Python workflow.
  float ax = bmi270.data.accelX * 9.80665;
  float ay = bmi270.data.accelY * 9.80665;
  float az = bmi270.data.accelZ * 9.80665;

  float gx = bmi270.data.gyroX;
  float gy = bmi270.data.gyroY;
  float gz = bmi270.data.gyroZ;

  printIMULine(ax, ay, az, gx, gy, gz);
#endif
}

void sendBNO08xAsIMU() {
#if USE_BNO08X
  if (!bno08xReady) return;

  // BNO08x accelerometer output is already m/s^2.
  // Gyroscope output is rad/s.
  printIMULine(bno_ax, bno_ay, bno_az, bno_gx, bno_gy, bno_gz);
#endif
}

void printIMULine(float ax, float ay, float az, float gx, float gy, float gz) {
  Serial.print("IMU:");
  Serial.print(millis());
  Serial.print(",");
  Serial.print(ax, 4);
  Serial.print(",");
  Serial.print(ay, 4);
  Serial.print(",");
  Serial.print(az, 4);
  Serial.print(",");
  Serial.print(gx, 4);
  Serial.print(",");
  Serial.print(gy, 4);
  Serial.print(",");
  Serial.println(gz, 4);
}

void sendAhrsData() {
#if USE_BNO08X
  if (!bno08xReady) return;

  Serial.print("AHRS:");
  Serial.print(millis());
  Serial.print(",");
  Serial.print(bno_ax, 4);
  Serial.print(",");
  Serial.print(bno_ay, 4);
  Serial.print(",");
  Serial.print(bno_az, 4);
  Serial.print(",");
  Serial.print(bno_gx, 4);
  Serial.print(",");
  Serial.print(bno_gy, 4);
  Serial.print(",");
  Serial.print(bno_gz, 4);
  Serial.print(",");
  Serial.print(bno_qw, 6);
  Serial.print(",");
  Serial.print(bno_qx, 6);
  Serial.print(",");
  Serial.print(bno_qy, 6);
  Serial.print(",");
  Serial.print(bno_qz, 6);
  Serial.print(",");
  Serial.println(bno_accuracy, 4);
#endif
}

// ---------------- Status / I2C Debug ----------------

void sendStatus() {
  Serial.print("STATUS:");

  for (int i = 0; i < MOTOR_COUNT; i++) {
    Serial.print("M");
    Serial.print(i + 1);
    Serial.print("=");
    Serial.print(motorState[i] ? "ON" : "OFF");

    if (i < MOTOR_COUNT - 1) {
      Serial.print(",");
    }
  }

  Serial.print(",BMI270=");
  Serial.print(bmi270Ready ? "OK" : "ERROR");

  Serial.print(",BNO08X=");
  Serial.print(bno08xReady ? "OK" : "ERROR");

  Serial.println();
}

void scanI2C() {
  Serial.println("I2C_SCAN_START");

  byte count = 0;

  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("I2C_DEVICE:0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
      count++;
    }
  }

  Serial.print("I2C_SCAN_COMPLETE:devices=");
  Serial.println(count);
}
