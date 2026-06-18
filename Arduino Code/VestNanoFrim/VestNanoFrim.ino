/*
  14-Motor Haptic Test Firmware
  Board: Arduino Nano for now
  Future: XIAO ESP32-C3 with mostly same serial protocol

  Commands:
    PING
    STOP
    MOTOR:1:180:1000
    PATTERN:ALL:180:1000
    PATTERN:ODD:180:1000
    PATTERN:EVEN:180:1000
    PATTERN:SWEEP:180:300
    PATTERN:FIRST_HALF:180:1000
    PATTERN:SECOND_HALF:180:1000
*/

const int NUM_MOTORS = 14;

// Change these to match your actual wiring.
// Nano pins D2-D13 + A0 + A1 = 14 outputs.
const int motorPins[NUM_MOTORS] = {
  2, 3, 4, 5, 6, 7, 8,
  9, 10, 11, 12, 13, A0, A1
};

// Set this true if your circuit is active-low.
// Active-low means LOW = motor ON, HIGH = motor OFF.
const bool ACTIVE_LOW = true;

String input = "";

void setup() {
  Serial.begin(115200);

  for (int i = 0; i < NUM_MOTORS; i++) {
    pinMode(motorPins[i], OUTPUT);
    motorOff(i);
  }

  Serial.println("READY:14_MOTOR_CONTROLLER");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      input.trim();
      handleCommand(input);
      input = "";
    } else {
      input += c;
    }
  }
}

void motorOn(int index, int intensity) {
  if (index < 0 || index >= NUM_MOTORS) return;

  intensity = constrain(intensity, 0, 255);

  if (ACTIVE_LOW) {
    analogWriteSafe(motorPins[index], 255 - intensity);
  } else {
    analogWriteSafe(motorPins[index], intensity);
  }
}

void motorOff(int index) {
  if (index < 0 || index >= NUM_MOTORS) return;

  if (ACTIVE_LOW) {
    digitalWrite(motorPins[index], HIGH);
  } else {
    digitalWrite(motorPins[index], LOW);
  }
}

void allOff() {
  for (int i = 0; i < NUM_MOTORS; i++) {
    motorOff(i);
  }
}

void analogWriteSafe(int pin, int value) {
  /*
    On Arduino Nano, only pins 3, 5, 6, 9, 10, 11 support PWM.
    For non-PWM pins, this becomes simple ON/OFF.
  */
  if (
    pin == 3 || pin == 5 || pin == 6 ||
    pin == 9 || pin == 10 || pin == 11
  ) {
    analogWrite(pin, value);
  } else {
    if (ACTIVE_LOW) {
      digitalWrite(pin, value < 255 ? LOW : HIGH);
    } else {
      digitalWrite(pin, value > 0 ? HIGH : LOW);
    }
  }
}

void runMotorTimed(int motorNumber, int intensity, int durationMs) {
  int index = motorNumber - 1;

  motorOn(index, intensity);
  delay(durationMs);
  motorOff(index);

  Serial.print("DONE:MOTOR:");
  Serial.println(motorNumber);
}

void runPattern(String pattern, int intensity, int durationMs) {
  pattern.toUpperCase();

  if (pattern == "ALL") {
    for (int i = 0; i < NUM_MOTORS; i++) motorOn(i, intensity);
    delay(durationMs);
    allOff();
  }

  else if (pattern == "ODD") {
    for (int i = 0; i < NUM_MOTORS; i += 2) motorOn(i, intensity);
    delay(durationMs);
    allOff();
  }

  else if (pattern == "EVEN") {
    for (int i = 1; i < NUM_MOTORS; i += 2) motorOn(i, intensity);
    delay(durationMs);
    allOff();
  }

  else if (pattern == "FIRST_HALF") {
    for (int i = 0; i < 7; i++) motorOn(i, intensity);
    delay(durationMs);
    allOff();
  }

  else if (pattern == "SECOND_HALF") {
    for (int i = 7; i < NUM_MOTORS; i++) motorOn(i, intensity);
    delay(durationMs);
    allOff();
  }

  else if (pattern == "SWEEP") {
    for (int i = 0; i < NUM_MOTORS; i++) {
      motorOn(i, intensity);
      delay(durationMs);
      motorOff(i);
    }
  }

  else {
    Serial.println("ERROR:UNKNOWN_PATTERN");
    return;
  }

  Serial.print("DONE:PATTERN:");
  Serial.println(pattern);
}

void handleCommand(String cmd) {
  cmd.trim();

  if (cmd == "PING") {
    Serial.println("PONG:14_MOTOR_CONTROLLER");
    return;
  }

  if (cmd == "STOP") {
    allOff();
    Serial.println("DONE:STOP");
    return;
  }

  if (cmd.startsWith("MOTOR:")) {
    int first = cmd.indexOf(':');
    int second = cmd.indexOf(':', first + 1);
    int third = cmd.indexOf(':', second + 1);

    int motorNumber = cmd.substring(first + 1, second).toInt();
    int intensity = cmd.substring(second + 1, third).toInt();
    int durationMs = cmd.substring(third + 1).toInt();

    runMotorTimed(motorNumber, intensity, durationMs);
    return;
  }

  if (cmd.startsWith("PATTERN:")) {
    int first = cmd.indexOf(':');
    int second = cmd.indexOf(':', first + 1);
    int third = cmd.indexOf(':', second + 1);

    String pattern = cmd.substring(first + 1, second);
    int intensity = cmd.substring(second + 1, third).toInt();
    int durationMs = cmd.substring(third + 1).toInt();

    runPattern(pattern, intensity, durationMs);
    return;
  }

  Serial.println("ERROR:UNKNOWN_COMMAND");
}