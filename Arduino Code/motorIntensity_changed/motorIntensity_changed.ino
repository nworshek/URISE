const int IN1 = 3;
const int IN2 = 5;
const int IN5 = 10;
const int IN6 = 11;


const int motors[] = {IN1, IN2, IN5, IN6};
const int numberMotor = 4;

void setup() {
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN5, OUTPUT);
  pinMode(IN6, OUTPUT);

  closeAll();
}

void loop() {

  for (int i = 0; i < numberMotor; i++) {

    closeAll();
  
    analogWrite(motors[i], 255); 

    delay(5000); 

  }
}


void closeAll() {
  analogWrite(IN1, 0);
  analogWrite(IN2, 0);
  analogWrite(IN5, 0);
  analogWrite(IN6, 0);
}