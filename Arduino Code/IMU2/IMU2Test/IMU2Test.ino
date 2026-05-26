#include <Wire.h>
#include <math.h>
#include <SparkFun_BMI270_Arduino_Library.h>

// Create BMI270 sensor object
BMI270 imu;

// I2C address
// Use 0x68 first. If it does not connect, try 0x69.
uint8_t i2cAddress = BMI2_I2C_PRIM_ADDR; // 0x68
// uint8_t i2cAddress = BMI2_I2C_SEC_ADDR; // 0x69

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000);

  delay(500);

  Serial.println("BMI270 IMU Data Logger Starting...");

  while (imu.beginI2C(i2cAddress) != BMI2_OK) {
    Serial.println("ERROR: BMI270 not connected. Check wiring or try address 0x69.");
    delay(1000);
  }

  Serial.println("BMI270 connected.");
  Serial.println("time_ms,accel_x_g,accel_y_g,accel_z_g,g_total,vibration_mg");
}

void loop() {
  imu.getSensorData();

  float accX = imu.data.accelX;
  float accY = imu.data.accelY;
  float accZ = imu.data.accelZ;

  float gTotal = sqrt(accX * accX + accY * accY + accZ * accZ);

  // Difference from 1g gravity baseline, converted to mg
  float vibrationMg = abs(gTotal - 1.0) * 1000.0;

  Serial.print(millis());
  Serial.print(",");
  Serial.print(accX, 4);
  Serial.print(",");
  Serial.print(accY, 4);
  Serial.print(",");
  Serial.print(accZ, 4);
  Serial.print(",");
  Serial.print(gTotal, 4);
  Serial.print(",");
  Serial.println(vibrationMg, 2);

  delay(20); // 50 samples per second
}