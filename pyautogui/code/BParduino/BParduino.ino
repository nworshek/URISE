/*
  Simplified BIOPAC Sync Arduino Firmware

  Purpose:
  - Waits for Python to send "GO"
  - Sends a TTL pulse from D7 to BIOPAC
  - Used with the simplified "SYNC NOW" Python GUI

  Wiring:
  - Arduino D7  -> BIOPAC trigger/event input
  - Arduino GND -> BIOPAC GND

  Baud rate: 115200
*/

const int BIOPAC_TRIGGER_PIN = 7;
const unsigned long PULSE_MS = 100;

String inputLine = "";

void setup() {
  Serial.begin(115200);

  pinMode(BIOPAC_TRIGGER_PIN, OUTPUT);
  digitalWrite(BIOPAC_TRIGGER_PIN, LOW);

  inputLine.reserve(40);

  Serial.println("READY:BIOPAC_SYNC");
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n' || c == '\r') {
      if (inputLine.length() > 0) {
        processCommand(inputLine);
        inputLine = "";
      }
    } else {
      inputLine += c;
    }
  }
}

void processCommand(String cmd) {
  cmd.trim();

  if (cmd == "GO") {
    sendPulse(PULSE_MS);
    Serial.println("ACK:GO");
    return;
  }

  if (cmd == "PING") {
    Serial.println("PONG:BIOPAC_SYNC");
    return;
  }

  if (cmd == "STATUS") {
    Serial.print("STATUS:TRIGGER_PIN=D");
    Serial.print(BIOPAC_TRIGGER_PIN);
    Serial.print(",PULSE_MS=");
    Serial.println(PULSE_MS);
    return;
  }

  Serial.print("ERROR:UNKNOWN_COMMAND:");
  Serial.println(cmd);
}

void sendPulse(unsigned long pulseMs) {
  digitalWrite(BIOPAC_TRIGGER_PIN, HIGH);
  delay(pulseMs);
  digitalWrite(BIOPAC_TRIGGER_PIN, LOW);
}