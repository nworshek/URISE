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
}

void loop() {
  if (Serial.available() > 0) {
    char cmd = Serial.read();

    // Motor 1
    if (cmd == '1') {
      pwm1 = 255;
      analogWrite(IN1, pwm1);
    }
    else if (cmd == '0') {
      pwm1 = 0;
      analogWrite(IN1, pwm1);
    }
    else if (cmd == 'A') {
      pwm1 = min(pwm1 + 10, 255);
      analogWrite(IN1, pwm1);
    }
    else if (cmd == 'a') {
      pwm1 = max(pwm1 - 10, 0);
      analogWrite(IN1, pwm1);
    }

    // Motor 2
    else if (cmd == '2') {
      pwm2 = 255;
      analogWrite(IN2, pwm2);
    }
    else if (cmd == 'q') {
      pwm2 = 0;
      analogWrite(IN2, pwm2);
    }
    else if (cmd == 'B') {
      pwm2 = min(pwm2 + 10, 255);
      analogWrite(IN2, pwm2);
    }
    else if (cmd == 'b') {
      pwm2 = max(pwm2 - 10, 0);
      analogWrite(IN2, pwm2);
    }

    // Motor 3
    else if (cmd == '3') {
      pwm3 = 255;
      analogWrite(IN3, pwm3);
    }
    else if (cmd == 'w') {
      pwm3 = 0;
      analogWrite(IN3, pwm3);
    }
    else if (cmd == 'C') {
      pwm3 = min(pwm3 + 10, 255);
      analogWrite(IN3, pwm3);
    }
    else if (cmd == 'c') {
      pwm3 = max(pwm3 - 10, 0);
      analogWrite(IN3, pwm3);
    }

    // Motor 4
    else if (cmd == '4') {
      pwm4 = 255;
      analogWrite(IN4, pwm4);
    }
    else if (cmd == 'e') {
      pwm4 = 0;
      analogWrite(IN4, pwm4);
    }
    else if (cmd == 'D') {
      pwm4 = min(pwm4 + 10, 255);
      analogWrite(IN4, pwm4);
    }
    else if (cmd == 'd') {
      pwm4 = max(pwm4 - 10, 0);
      analogWrite(IN4, pwm4);
    }

    // Motor 5
    else if (cmd == '5') {
      pwm5 = 255;
      analogWrite(IN5, pwm5);
    }
    else if (cmd == 'r') {
      pwm5 = 0;
      analogWrite(IN5, pwm5);
    }
    else if (cmd == 'E') {
      pwm5 = min(pwm5 + 10, 255);
      analogWrite(IN5, pwm5);
    }
    else if (cmd == 'f') {
      pwm5 = max(pwm5 - 10, 0);
      analogWrite(IN5, pwm5);
    }

    // Motor 6
    else if (cmd == '6') {
      pwm6 = 255;
      analogWrite(IN6, pwm6);
    }
    else if (cmd == 't') {
      pwm6 = 0;
      analogWrite(IN6, pwm6);
    }
    else if (cmd == 'F') {
      pwm6 = min(pwm6 + 10, 255);
      analogWrite(IN6, pwm6);
    }
    else if (cmd == 'g') {
      pwm6 = max(pwm6 - 10, 0);
      analogWrite(IN6, pwm6);
    }
  }
}