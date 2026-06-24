#include <Wire.h>

void setup() {
  Serial.begin(115200);
  Wire.begin();

  Wire.beginTransmission(0x40);
  if (Wire.endTransmission() == 0)
    Serial.println("PCA9685 Found");
  else
    Serial.println("PCA9685 Not Found");
}

void loop() {}