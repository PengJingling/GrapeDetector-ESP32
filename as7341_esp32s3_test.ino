#include <Wire.h>
#include <Adafruit_AS7341.h>

// ESP32-S3-DevKitC-1 recommended I2C wiring:
// AS7341 SDA -> GPIO8, AS7341 SCL -> GPIO9, VIN -> 3V3, GND -> GND.
constexpr int SDA_PIN = 8;
constexpr int SCL_PIN = 9;

Adafruit_AS7341 as7341;

void printHeader() {
  Serial.println("F1_415,F2_445,F3_480,F4_515,F5_555,F6_590,F7_630,F8_680,CLEAR,NIR");
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(SDA_PIN, SCL_PIN);

  if (!as7341.begin(0x39, &Wire)) {
    Serial.println("AS7341 not found. Check VIN/GND/SDA/SCL wiring.");
    while (true) {
      delay(1000);
    }
  }

  as7341.setATIME(100);
  as7341.setASTEP(999);
  as7341.setGain(AS7341_GAIN_16X);

  // Enable only if your AS7341 breakout has an onboard LED connected to the LED pin.
  as7341.setLEDCurrent(4);
  as7341.enableLED(true);

  printHeader();
}

void loop() {
  if (!as7341.readAllChannels()) {
    Serial.println("read_failed");
    delay(500);
    return;
  }

  Serial.print(as7341.getChannel(AS7341_CHANNEL_415nm_F1));
  Serial.print(",");
  Serial.print(as7341.getChannel(AS7341_CHANNEL_445nm_F2));
  Serial.print(",");
  Serial.print(as7341.getChannel(AS7341_CHANNEL_480nm_F3));
  Serial.print(",");
  Serial.print(as7341.getChannel(AS7341_CHANNEL_515nm_F4));
  Serial.print(",");
  Serial.print(as7341.getChannel(AS7341_CHANNEL_555nm_F5));
  Serial.print(",");
  Serial.print(as7341.getChannel(AS7341_CHANNEL_590nm_F6));
  Serial.print(",");
  Serial.print(as7341.getChannel(AS7341_CHANNEL_630nm_F7));
  Serial.print(",");
  Serial.print(as7341.getChannel(AS7341_CHANNEL_680nm_F8));
  Serial.print(",");
  Serial.print(as7341.getChannel(AS7341_CHANNEL_CLEAR));
  Serial.print(",");
  Serial.println(as7341.getChannel(AS7341_CHANNEL_NIR));

  delay(500);
}
