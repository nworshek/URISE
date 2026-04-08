// Motor Intensity Arduino Firmware for Arduino IDE

const int IN1 = 3;
const int IN2 = 5;
const int IN3 = 6;
const int IN4 = 9;
const int IN5 = 10;
const int IN6 = 11;

int pwm1 = 0;
int pwm2 = 0;
int pwm3 = 0;
int pwm4 = 0;
int pwm5 = 0;
int pwm6 = 0;

String inputString = "";
bool stringComplete = false;

void setup() {
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  pinMode(IN5, OUTPUT);
  pinMode(IN6, OUTPUT);

  analogWrite(IN1, 0);
  analogWrite(IN2, 0);
  analogWrite(IN3, 0);
  analogWrite(IN4, 0);
  analogWrite(IN5, 0);
  analogWrite(IN6, 0);

  Serial.begin(9600);
  inputString.reserve(20);
}

void loop() {
  if (stringComplete) {
    processCommand(inputString);
    inputString = "";
    stringComplete = false;
  }
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();

    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
}

void processCommand(String cmd) {
  cmd.trim();

  int separator = cmd.indexOf(':');
  if (separator == -1) return;

  int motor = cmd.substring(0, separator).toInt();
  int value = cmd.substring(separator + 1).toInt();

  value = constrain(value, 0, 255);

  if (motor == 1) {
    pwm1 = value;
    analogWrite(IN1, pwm1);
  }
  else if (motor == 2) {
    pwm2 = value;
    analogWrite(IN2, pwm2);
  }
  else if (motor == 3) {
    pwm3 = value;
    analogWrite(IN3, pwm3);
  }
  else if (motor == 4) {
    pwm4 = value;
    analogWrite(IN4, pwm4);
  }
  else if (motor == 5) {
    pwm5 = value;
    analogWrite(IN5, pwm5);
  }
  else if (motor == 6) {
    pwm6 = value;
    analogWrite(IN6, pwm6);
  }
}
