/*
  ESP32-C6 IMU Streaming Firmware
  For Python IMU Validation Software

  Output format:
  IMU9:<timestamp>,
  s1_ax,s1_ay,s1_az,s1_gx,s1_gy,s1_gz,s1_mx,s1_my,s1_mz,
  s2_ax,s2_ay,s2_az,s2_gx,s2_gy,s2_gz,s2_mx,s2_my,s2_mz,
  s3_ax,s3_ay,s3_az,s3_gx,s3_gy,s3_gz,s3_mx,s3_my,s3_mz,
  s4_ax,s4_ay,s4_az,s4_gx,s4_gy,s4_gz,s4_mx,s4_my,s4_mz,
  s5_ax,s5_ay,s5_az,s5_gx,s5_gy,s5_gz,s5_mx,s5_my,s5_mz

  Sensor slot plan:
  Sensor 1 = SparkFun BMI270
  Sensor 2 = BNO080/BNO085-style AR/VR 9DOF module
  Sensor 3 = empty placeholder
  Sensor 4 = empty placeholder
  Sensor 5 = empty placeholder
*/

#include <Wire.h>

// BMI270
#include "SparkFun_BMI270_Arduino_Library.h"

// BNO08x / BNO085
#include <Adafruit_BNO08x.h>

// ---------------- USER SETTINGS ----------------

#define SERIAL_BAUD 115200

// Change these if your ESP32-C6 board uses different I2C pins.
#define SDA_PIN 6
#define SCL_PIN 7

// Sample rate.
// 20 ms = 50 Hz
// 40 ms = 25 Hz
// 100 ms = 10 Hz
// 250 ms = 4 Hz
const unsigned long sampleIntervalMs = 20;

// I2C addresses
const uint8_t BMI270_ADDR = BMI2_I2C_PRIM_ADDR; // Usually 0x68
const uint8_t BNO08X_ADDR = 0x4A;               // Usually 0x4A or 0x4B

// ---------------- SENSOR OBJECTS ----------------

BMI270 bmi270;
Adafruit_BNO08x bno08x(-1);
sh2_SensorValue_t bnoSensorValue;

// ---------------- STATE ----------------

bool bmi270Ready = false;
bool bno08xReady = false;

unsigned long lastSampleMillis = 0;

// Sensor data storage: 5 sensors x 9 values
// Axis order per sensor:
// ax, ay, az, gx, gy, gz, mx, my, mz
float sensorData[5][9];

// ---------------- SETUP ----------------

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);

  Wire.begin(SDA_PIN, SCL_PIN);
  delay(100);

  clearAllSensorData();

  Serial.println("FIRMWARE:ESP32C6_IMU9_STREAMER");
  Serial.println("READY");

  scanI2C();

  setupBMI270();
  setupBNO08x();

  Serial.println("IMU_SETUP_COMPLETE");
}

// ---------------- LOOP ----------------

void loop() {
  handleSerialCommands();

  unsigned long now = millis();

  if (now - lastSampleMillis >= sampleIntervalMs) {
    lastSampleMillis = now;

    clearAllSensorData();

    readBMI270();
    readBNO08x();

    sendIMU9Packet();
  }
}

// ---------------- SERIAL COMMANDS ----------------

void handleSerialCommands() {
  if (!Serial.available()) {
    return;
  }

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "PING") {
    Serial.println("READY");
  }

  else if (cmd == "SCAN") {
    scanI2C();
  }

  else if (cmd == "STATUS") {
    sendStatus();
  }
}

// ---------------- I2C SCAN ----------------

void scanI2C() {
  Serial.println("I2C_SCAN_START");

  byte count = 0;

  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("I2C_DEVICE_FOUND:0x");

      if (address < 16) {
        Serial.print("0");
      }

      Serial.println(address, HEX);
      count++;
    }
  }

  Serial.print("I2C_SCAN_COMPLETE:");
  Serial.print(count);
  Serial.println("_DEVICE(S)");
}

// ---------------- SENSOR SETUP ----------------

void setupBMI270() {
  Serial.println("BMI270_SETUP_START");

  while (bmi270.beginI2C(BMI270_ADDR) != BMI2_OK) {
    Serial.println("ERROR:BMI270_NOT_FOUND");
    bmi270Ready = false;
    delay(1000);
    return;
  }

  bmi270Ready = true;
  Serial.println("BMI270_READY");
}

void setupBNO08x() {
  Serial.println("BNO08X_SETUP_START");

  if (!bno08x.begin_I2C(BNO08X_ADDR, &Wire)) {
    Serial.println("ERROR:BNO08X_NOT_FOUND");
    bno08xReady = false;
    return;
  }

  bno08xReady = true;

  // Enable accelerometer
  if (!bno08x.enableReport(SH2_ACCELEROMETER)) {
    Serial.println("ERROR:BNO08X_ACCEL_REPORT_FAILED");
  }

  // Enable gyroscope
  if (!bno08x.enableReport(SH2_GYROSCOPE_CALIBRATED)) {
    Serial.println("ERROR:BNO08X_GYRO_REPORT_FAILED");
  }

  // Enable magnetometer
  if (!bno08x.enableReport(SH2_MAGNETIC_FIELD_CALIBRATED)) {
    Serial.println("ERROR:BNO08X_MAG_REPORT_FAILED");
  }

  Serial.println("BNO08X_READY");
}

// ---------------- READ SENSORS ----------------

void readBMI270() {
  if (!bmi270Ready) {
    return;
  }

  bmi270.getSensorData();

  // Sensor slot 1
  // BMI270 is 6-axis only, so magnetometer values are 0.
  sensorData[0][0] = bmi270.data.accelX;
  sensorData[0][1] = bmi270.data.accelY;
  sensorData[0][2] = bmi270.data.accelZ;

  sensorData[0][3] = bmi270.data.gyroX;
  sensorData[0][4] = bmi270.data.gyroY;
  sensorData[0][5] = bmi270.data.gyroZ;

  sensorData[0][6] = 0.0;
  sensorData[0][7] = 0.0;
  sensorData[0][8] = 0.0;
}

void readBNO08x() {
  if (!bno08xReady) {
    return;
  }

  // Read all currently available BNO08x reports.
  while (bno08x.getSensorEvent(&bnoSensorValue)) {

    // Sensor slot 2
    switch (bnoSensorValue.sensorId) {

      case SH2_ACCELEROMETER:
        sensorData[1][0] = bnoSensorValue.un.accelerometer.x;
        sensorData[1][1] = bnoSensorValue.un.accelerometer.y;
        sensorData[1][2] = bnoSensorValue.un.accelerometer.z;
        break;

      case SH2_GYROSCOPE_CALIBRATED:
        sensorData[1][3] = bnoSensorValue.un.gyroscope.x;
        sensorData[1][4] = bnoSensorValue.un.gyroscope.y;
        sensorData[1][5] = bnoSensorValue.un.gyroscope.z;
        break;

      case SH2_MAGNETIC_FIELD_CALIBRATED:
        sensorData[1][6] = bnoSensorValue.un.magneticField.x;
        sensorData[1][7] = bnoSensorValue.un.magneticField.y;
        sensorData[1][8] = bnoSensorValue.un.magneticField.z;
        break;
    }
  }
}

// ---------------- SEND DATA ----------------

void sendIMU9Packet() {
  Serial.print("IMU9:");
  Serial.print(millis());

  for (int sensor = 0; sensor < 5; sensor++) {
    for (int axis = 0; axis < 9; axis++) {
      Serial.print(",");
      Serial.print(sensorData[sensor][axis], 4);
    }
  }

  Serial.println();
}

void sendStatus() {
  Serial.print("STATUS:");
  Serial.print("BMI270=");
  Serial.print(bmi270Ready ? "READY" : "NOT_FOUND");

  Serial.print(",BNO08X=");
  Serial.print(bno08xReady ? "READY" : "NOT_FOUND");

  Serial.print(",SAMPLE_INTERVAL_MS=");
  Serial.println(sampleIntervalMs);
}

// ---------------- HELPERS ----------------

void clearAllSensorData() {
  for (int sensor = 0; sensor < 5; sensor++) {
    for (int axis = 0; axis < 9; axis++) {
      sensorData[sensor][axis] = 0.0;
    }
  }
}