#include <Wire.h>
#include <math.h>  // Needed for sqrt() and abs()

#define BMI2_ADDR 0x68 // Try 0x69 if it doesn’t work

void setup() {
  Serial.begin(115200);
  Wire.begin();

  Serial.println(F("--- FORCED UNLOCK BMI270 ---"));

  // 1. Software reset
  Wire.beginTransmission(BMI2_ADDR);
  Wire.write(0x7E);
  Wire.write(0xB6);
  Wire.endTransmission();
  delay(100);

  // 2. Exit Suspend Mode (PWR_CONF)
  // Disable advanced power save (bit 0) and enable fast startup (bit 1)
  Wire.beginTransmission(BMI2_ADDR);
  Wire.write(0x7C);
  Wire.write(0x02);
  Wire.endTransmission();
  delay(50);

  // 3. Load "fake" configuration

  // Tell the sensor we are about to load configuration (INIT_CTRL)
  Wire.beginTransmission(BMI2_ADDR);
  Wire.write(0x59);
  Wire.write(0x00);
  Wire.endTransmission();

  // Set range and speed (ACC_CONF)
  // 0xA8 = 4G range, 100Hz output data rate, optimized performance
  Wire.beginTransmission(BMI2_ADDR);
  Wire.write(0x40);
  Wire.write(0xA8);
  Wire.endTransmission();

  // 4. Enable power to the accelerometer (PWR_CTRL)
  Wire.beginTransmission(BMI2_ADDR);
  Wire.write(0x7D);
  Wire.write(0x04);
  Wire.endTransmission();

  Serial.println(F("Test: shake the sensor. If you see changes, the unlock worked!"));
}

void loop() {
  Wire.beginTransmission(BMI2_ADDR);
  Wire.write(0x0C); // Accelerometer data register
  Wire.endTransmission(false);
  Wire.requestFrom(BMI2_ADDR, 6);

  if (Wire.available() == 6) {
    int16_t ax = Wire.read() | (Wire.read() << 8);
    int16_t ay = Wire.read() | (Wire.read() << 8);
    int16_t az = Wire.read() | (Wire.read() << 8);

    // Conversion for 4G range (8192 LSB/g)
    float fax = ax / 8192.0;
    float fay = ay / 8192.0;
    float faz = az / 8192.0;

    float forzaG = sqrt(fax * fax + fay * fay + faz * faz); // Total G force

    // Show vibration difference relative to 1.0G (gravity baseline)
    float vibrazione = abs(forzaG - 1.0) * 1000.0; // in mg

    Serial.print(F("G_Total:"));
    Serial.print(forzaG, 3);

    Serial.print(F("\tVibration_mg:"));
    Serial.println(vibrazione, 1);
  }

  delay(100);
}