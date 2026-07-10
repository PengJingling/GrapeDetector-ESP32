#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"
#include <Adafruit_AS7341.h>

#include "config.h"

Adafruit_AS7341 as7341;
WebServer server(80);
WiFiServer streamServer(CAMERA_STREAM_PORT);
HardwareSerial stm32Serial(1);
bool as7341Ready = false;
bool cameraReady = false;
esp_err_t cameraInitError = ESP_OK;
uint32_t captureFailCount = 0;
SemaphoreHandle_t cameraMutex = nullptr;
int cameraBrightness = CAMERA_DEFAULT_BRIGHTNESS;
bool manualExposure = CAMERA_DEFAULT_MANUAL_EXPOSURE;
int cameraAecValue = CAMERA_DEFAULT_AEC_VALUE;
int cameraAgcGain = CAMERA_DEFAULT_AGC_GAIN;
bool cameraFlashOn = false;
String stm32LineBuffer;
String lastStm32Line = "";
unsigned long lastStm32LineMs = 0;

struct SpectrumSample {
  bool ok = false;
  uint16_t f1_415 = 0;
  uint16_t f2_445 = 0;
  uint16_t f3_480 = 0;
  uint16_t f4_515 = 0;
  uint16_t f5_555 = 0;
  uint16_t f6_590 = 0;
  uint16_t f7_630 = 0;
  uint16_t f8_680 = 0;
  uint16_t clear = 0;
  uint16_t nir = 0;
};

static camera_fb_t *captureFrame(framesize_t frameSize);
static camera_fb_t *captureFrameAdvanced(framesize_t frameSize, int settleMs, int discardCount, int retryCount);
static void releaseFrame(camera_fb_t *fb);

static String ipToString(IPAddress ip) {
  return String(ip[0]) + "." + String(ip[1]) + "." + String(ip[2]) + "." + String(ip[3]);
}

static String jsonEscape(const String &value) {
  String out;
  out.reserve(value.length() + 8);
  for (size_t i = 0; i < value.length(); i++) {
    char c = value[i];
    if (c == '"' || c == '\\') {
      out += '\\';
      out += c;
    } else if (c == '\r') {
      out += "\\r";
    } else if (c == '\n') {
      out += "\\n";
    } else {
      out += c;
    }
  }
  return out;
}

static void setWhiteLed(bool on) {
#if WHITE_LED_PIN >= 0
  digitalWrite(WHITE_LED_PIN, on == WHITE_LED_ACTIVE_HIGH ? HIGH : LOW);
#else
  (void)on;
#endif
}

static void setCameraFlash(bool on) {
  cameraFlashOn = on;
#if CAMERA_FLASH_PIN >= 0
  digitalWrite(CAMERA_FLASH_PIN, on == CAMERA_FLASH_ACTIVE_HIGH ? HIGH : LOW);
#else
  (void)on;
#endif
}

static int clampInt(int value, int minValue, int maxValue) {
  if (value < minValue) {
    return minValue;
  }
  if (value > maxValue) {
    return maxValue;
  }
  return value;
}

static void applyCameraTuning(sensor_t *sensor) {
  if (!sensor) {
    return;
  }

  sensor->set_quality(sensor, CAMERA_JPEG_QUALITY);
  sensor->set_brightness(sensor, cameraBrightness);
  sensor->set_contrast(sensor, 0);
  sensor->set_saturation(sensor, 0);
  sensor->set_gain_ctrl(sensor, manualExposure ? 0 : 1);
  sensor->set_exposure_ctrl(sensor, manualExposure ? 0 : 1);
  if (manualExposure) {
    sensor->set_aec_value(sensor, cameraAecValue);
    sensor->set_agc_gain(sensor, cameraAgcGain);
  }
  sensor->set_whitebal(sensor, 1);
  sensor->set_awb_gain(sensor, 1);
}

static bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = CAM_PIN_D0;
  config.pin_d1 = CAM_PIN_D1;
  config.pin_d2 = CAM_PIN_D2;
  config.pin_d3 = CAM_PIN_D3;
  config.pin_d4 = CAM_PIN_D4;
  config.pin_d5 = CAM_PIN_D5;
  config.pin_d6 = CAM_PIN_D6;
  config.pin_d7 = CAM_PIN_D7;
  config.pin_xclk = CAM_PIN_XCLK;
  config.pin_pclk = CAM_PIN_PCLK;
  config.pin_vsync = CAM_PIN_VSYNC;
  config.pin_href = CAM_PIN_HREF;
  config.pin_sccb_sda = CAM_PIN_SIOD;
  config.pin_sccb_scl = CAM_PIN_SIOC;
  config.pin_pwdn = CAM_PIN_PWDN;
  config.pin_reset = CAM_PIN_RESET;
  config.xclk_freq_hz = CAMERA_XCLK_FREQ_HZ;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = psramFound() ? CAMERA_HIGHRES_FRAME_SIZE : CAMERA_STREAM_FRAME_SIZE;
  config.jpeg_quality = CAMERA_JPEG_QUALITY;
  config.fb_count = psramFound() ? 2 : 1;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode = psramFound() ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;

  cameraInitError = esp_camera_init(&config);
  if (cameraInitError != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\r\n", cameraInitError);
    cameraReady = false;
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor) {
    sensor->set_framesize(sensor, CAMERA_STREAM_FRAME_SIZE);
    applyCameraTuning(sensor);
  }

  Serial.println("Camera init OK");
  cameraReady = true;
  return true;
}

static bool initAs7341() {
#if AS7341_DIRECT_TO_ESP32
  Wire.begin(AS7341_SDA_PIN, AS7341_SCL_PIN);
  Wire.setClock(100000);

  if (!as7341.begin(AS7341_I2CADDR_DEFAULT, &Wire)) {
    Serial.println("AS7341 not found. Check 3V3/GND/SDA/SCL.");
    return false;
  }

  as7341.setATIME(100);
  as7341.setASTEP(999);
  as7341.setGain(AS7341_GAIN_256X);
  Serial.println("AS7341 init OK");
  return true;
#else
  Serial.println("AS7341 direct ESP32 mode disabled.");
  Serial.println("PCB version connects AS7341 to STM32 PB6/PB7, or you can wire it to ESP32 GPIO19/GPIO41 and set AS7341_DIRECT_TO_ESP32=1.");
  return false;
#endif
}

static SpectrumSample readSpectrum() {
  SpectrumSample s;
#if !AS7341_DIRECT_TO_ESP32
  Serial.println("AS7341 is not directly connected to ESP32 in current config.");
  return s;
#else
  if (!as7341Ready) {
    Serial.println("AS7341 not ready.");
    return s;
  }

  uint16_t readings[12];

  setWhiteLed(true);
  delay(80);

  if (!as7341.readAllChannels(readings)) {
    Serial.println("AS7341 read failed");
    setWhiteLed(false);
    return s;
  }

  s.ok = true;
  s.f1_415 = readings[AS7341_CHANNEL_415nm_F1];
  s.f2_445 = readings[AS7341_CHANNEL_445nm_F2];
  s.f3_480 = readings[AS7341_CHANNEL_480nm_F3];
  s.f4_515 = readings[AS7341_CHANNEL_515nm_F4];
  s.f5_555 = readings[AS7341_CHANNEL_555nm_F5];
  s.f6_590 = readings[AS7341_CHANNEL_590nm_F6];
  s.f7_630 = readings[AS7341_CHANNEL_630nm_F7];
  s.f8_680 = readings[AS7341_CHANNEL_680nm_F8];
  s.clear = readings[AS7341_CHANNEL_CLEAR];
  s.nir = readings[AS7341_CHANNEL_NIR];

  setWhiteLed(false);
  return s;
#endif
}

static String spectrumToJson(const SpectrumSample &s) {
  String json = "{";
  json += "\"ok\":" + String(s.ok ? "true" : "false");
  if (!s.ok) {
#if AS7341_DIRECT_TO_ESP32
    json += ",\"reason\":\"AS7341 not ready or read failed\"";
#else
    json += ",\"reason\":\"AS7341 direct ESP32 mode disabled; PCB connects AS7341 to STM32 PB6/PB7\"";
#endif
  }
  json += ",\"F1_415\":" + String(s.f1_415);
  json += ",\"F2_445\":" + String(s.f2_445);
  json += ",\"F3_480\":" + String(s.f3_480);
  json += ",\"F4_515\":" + String(s.f4_515);
  json += ",\"F5_555\":" + String(s.f5_555);
  json += ",\"F6_590\":" + String(s.f6_590);
  json += ",\"F7_630\":" + String(s.f7_630);
  json += ",\"F8_680\":" + String(s.f8_680);
  json += ",\"CLEAR\":" + String(s.clear);
  json += ",\"NIR\":" + String(s.nir);
  json += "}";
  return json;
}

static String stm32ToJson() {
  bool fresh = lastStm32Line.length() > 0 && millis() - lastStm32LineMs < 10000;
  String json = "{";
  json += "\"ok\":" + String(lastStm32Line.length() > 0 ? "true" : "false");
  json += ",\"fresh\":" + String(fresh ? "true" : "false");
  json += ",\"age_ms\":" + String(lastStm32Line.length() > 0 ? millis() - lastStm32LineMs : 0);
  json += ",\"raw\":\"" + jsonEscape(lastStm32Line) + "\"";
  json += "}";
  return json;
}

static String scanSccbToJson() {
  Wire.begin(CAM_PIN_SIOD, CAM_PIN_SIOC);
  Wire.setClock(100000);

  String json = "{";
  json += "\"sda\":" + String(CAM_PIN_SIOD);
  json += ",\"scl\":" + String(CAM_PIN_SIOC);
  json += ",\"addresses\":[";

  bool first = true;
  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();
    if (error == 0) {
      if (!first) {
        json += ",";
      }
      json += "\"0x";
      if (address < 16) {
        json += "0";
      }
      json += String(address, HEX);
      json += "\"";
      first = false;
    }
    delay(2);
  }

  json += "]";
  json += ",\"hint\":\"OV camera SCCB is usually 0x30 if clock, power, SDA and SCL are correct\"";
  json += "}";
  return json;
}

static int readReg8(uint8_t address, uint8_t reg) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return -1;
  }

  if (Wire.requestFrom((int)address, 1) != 1) {
    return -1;
  }
  return Wire.read();
}

static int readReg16(uint8_t address, uint16_t reg) {
  Wire.beginTransmission(address);
  Wire.write((uint8_t)(reg >> 8));
  Wire.write((uint8_t)(reg & 0xff));
  if (Wire.endTransmission(false) != 0) {
    return -1;
  }

  if (Wire.requestFrom((int)address, 1) != 1) {
    return -1;
  }
  return Wire.read();
}

static String hexByteOrNull(int value) {
  if (value < 0) {
    return "null";
  }
  String out = "\"0x";
  if (value < 16) {
    out += "0";
  }
  out += String(value, HEX);
  out += "\"";
  return out;
}

static String cameraIdToJson() {
  Wire.begin(CAM_PIN_SIOD, CAM_PIN_SIOC);
  Wire.setClock(100000);

  const uint8_t addr = 0x30;
  int reg0a = readReg8(addr, 0x0a);
  int reg0b = readReg8(addr, 0x0b);
  int reg300a = readReg16(addr, 0x300a);
  int reg300b = readReg16(addr, 0x300b);

  String guess = "unknown";
  if (reg0a == 0x26) {
    guess = "OV2640-like";
  } else if (reg300a == 0x56 && reg300b == 0x40) {
    guess = "OV5640";
  }

  String json = "{";
  json += "\"addr\":\"0x30\"";
  json += ",\"reg_0x0a\":" + hexByteOrNull(reg0a);
  json += ",\"reg_0x0b\":" + hexByteOrNull(reg0b);
  json += ",\"reg_0x300a\":" + hexByteOrNull(reg300a);
  json += ",\"reg_0x300b\":" + hexByteOrNull(reg300b);
  json += ",\"guess\":\"" + guess + "\"";
  json += "}";
  return json;
}

static void printSpectrumCsv(const SpectrumSample &s) {
  Serial.println("F1_415,F2_445,F3_480,F4_515,F5_555,F6_590,F7_630,F8_680,CLEAR,NIR");
  Serial.printf("%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\r\n",
                s.f1_415, s.f2_445, s.f3_480, s.f4_515, s.f5_555,
                s.f6_590, s.f7_630, s.f8_680, s.clear, s.nir);
}

static bool captureToSerial() {
  camera_fb_t *fb = captureFrame(CAMERA_SNAPSHOT_FRAME_SIZE);
  if (!fb) {
    Serial.println("Capture failed");
    return false;
  }
  Serial.printf("Capture OK: %u bytes, %ux%u\r\n", fb->len, fb->width, fb->height);
  releaseFrame(fb);
  return true;
}

static camera_fb_t *captureFrame(framesize_t frameSize) {
  return captureFrameAdvanced(frameSize, 180, 2, 1);
}

static camera_fb_t *captureFrameAdvanced(framesize_t frameSize, int settleMs, int discardCount, int retryCount) {
  if (cameraMutex && xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(2500)) != pdTRUE) {
    captureFailCount++;
    return nullptr;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor) {
    sensor->set_framesize(sensor, frameSize);
    applyCameraTuning(sensor);
    delay(settleMs);
    for (int i = 0; i < discardCount; i++) {
      camera_fb_t *discard = esp_camera_fb_get();
      if (discard) {
        esp_camera_fb_return(discard);
      }
      delay(40);
    }
  }

  camera_fb_t *fb = nullptr;
  for (int i = 0; i < retryCount && !fb; i++) {
    fb = esp_camera_fb_get();
    if (!fb) {
      delay(120);
    }
  }
  if (!fb) {
    captureFailCount++;
    if (cameraMutex) {
      xSemaphoreGive(cameraMutex);
    }
  }
  return fb;
}

static void releaseFrame(camera_fb_t *fb) {
  if (fb) {
    esp_camera_fb_return(fb);
  }
  if (cameraMutex) {
    xSemaphoreGive(cameraMutex);
  }
}

static void handleRoot() {
  String html;
  html += "<!doctype html><html><head><meta charset='utf-8'>";
  html += "<title>Grape Detector</title></head><body>";
  html += "<h2>Grape Detector ESP32-S3</h2>";
  html += "<p><a href='/live'>live monitor</a></p>";
  html += "<p><a href='/capture.jpg'>capture.jpg</a></p>";
  html += "<p><a href='/capture-vga.jpg'>capture-vga.jpg</a></p>";
  html += "<p><a href='/capture-svga.jpg'>capture-svga.jpg</a></p>";
  html += "<p><a href='/capture-xga.jpg'>capture-xga.jpg</a></p>";
  html += "<p><a href='/capture-sxga.jpg'>capture-sxga.jpg</a></p>";
  html += "<p><a href='/capture-uxga.jpg'>capture-uxga.jpg</a></p>";
  html += "<p><a href='/spectrum.json'>spectrum.json</a></p>";
  html += "<p><a href='/stm32.json'>stm32.json</a></p>";
  html += "<p><a href='/data.json'>data.json</a></p>";
  html += "<img src='/capture.jpg' style='max-width:100%;height:auto'>";
  html += "</body></html>";
  server.send(200, "text/html; charset=utf-8", html);
}

static void handleLivePage() {
  String html;
  html += "<!doctype html><html><head><meta charset='utf-8'>";
  html += "<meta name='viewport' content='width=device-width,initial-scale=1'>";
  html += "<title>Grape Live Monitor</title>";
  html += "<style>";
  html += "body{margin:0;background:#111;color:#eee;font-family:Arial,sans-serif;}";
  html += "main{max-width:860px;margin:0 auto;padding:16px;}";
  html += ".stage{background:#000;padding:12px;text-align:center;}";
  html += "img{width:640px;max-width:100%;height:auto;background:#000;}";
  html += "a,button{color:#111;background:#eee;border:0;padding:8px 12px;margin-right:8px;text-decoration:none;}";
  html += "p{line-height:1.6}";
  html += "</style></head><body><main>";
  html += "<h2>Grape Live Monitor</h2>";
  html += "<p><a href='/capture-uxga.jpg' target='_blank'>UXGA Snapshot</a><a href='/capture-sxga.jpg' target='_blank'>SXGA Snapshot</a><a href='/capture-xga.jpg' target='_blank'>XGA Snapshot</a><a href='/capture-svga.jpg' target='_blank'>SVGA Snapshot</a><a href='/capture-vga.jpg' target='_blank'>VGA Snapshot</a><a href='/capture.jpg' target='_blank'>QVGA Snapshot</a><a href='/health' target='_blank'>Health</a></p>";
  html += "<p>";
  html += "<button onclick='setBrightness(-2)'>最暗</button>";
  html += "<button onclick='setBrightness(-1)'>暗一点</button>";
  html += "<button onclick='setBrightness(0)'>正常</button>";
  html += "<button onclick='setBrightness(1)'>亮一点</button>";
  html += "<button onclick='setBrightness(2)'>最亮</button>";
  html += "<span id='brightness'> brightness=";
  html += String(cameraBrightness);
  html += "</span></p>";
  html += "<p>";
  html += "<button onclick='setExposure(\"auto\")'>自动曝光</button>";
  html += "<button onclick='setExposure(\"low\")'>低曝光</button>";
  html += "<button onclick='setExposure(\"mid\")'>中曝光</button>";
  html += "<button onclick='setExposure(\"high\")'>高曝光</button>";
  html += "<span id='exposure'> exposure=";
  if (manualExposure) {
    html += "manual aec=";
    html += String(cameraAecValue);
    html += " gain=";
    html += String(cameraAgcGain);
  } else {
    html += "auto";
  }
  html += "</span></p>";
  html += "<p>";
  html += "<button onclick='setFlash(1)'>打开补光灯</button>";
  html += "<button onclick='setFlash(0)'>关闭补光灯</button>";
  html += "<span id='flash'> flash=";
  html += cameraFlashOn ? "on" : "off";
  html += "</span></p>";
  html += "<div class='stage'><img id='frame' src='http://192.168.4.1:";
  html += String(CAMERA_STREAM_PORT);
  html += "/stream' alt='live stream'></div>";
  html += "<p>实时流使用 81 端口，普通接口仍在 80 端口，所以 /health 和 /capture.jpg 可以同时打开。</p>";
  html += "<script>";
  html += "async function setBrightness(v){await fetch('/control?brightness='+v);document.getElementById('brightness').textContent=' brightness='+v;}";
  html += "async function setExposure(m){const r=await fetch('/exposure?mode='+m);const j=await r.json();document.getElementById('exposure').textContent=' exposure='+(j.manual?'manual aec='+j.aec_value+' gain='+j.agc_gain:'auto');}";
  html += "async function setFlash(v){await fetch('/flash?on='+v);document.getElementById('flash').textContent=' flash='+(v?'on':'off');}";
  html += "</script>";
  html += "</main></body></html>";
  server.send(200, "text/html; charset=utf-8", html);
}

static void handleCaptureJpg() {
  camera_fb_t *fb = captureFrame(CAMERA_STREAM_FRAME_SIZE);
  if (!fb) {
    String message = "Capture failed\n";
    message += "camera_ready=" + String(cameraReady ? "true" : "false") + "\n";
    message += "camera_init_error=0x" + String((uint32_t)cameraInitError, HEX) + "\n";
    message += "capture_fail_count=" + String(captureFailCount) + "\n";
    server.send(500, "text/plain", message);
    return;
  }

  WiFiClient client = server.client();
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  client.write(fb->buf, fb->len);
  releaseFrame(fb);
}

static void handleCaptureVgaJpg() {
  camera_fb_t *fb = captureFrame(CAMERA_SNAPSHOT_FRAME_SIZE);
  if (!fb) {
    String message = "VGA capture failed\n";
    message += "camera_ready=" + String(cameraReady ? "true" : "false") + "\n";
    message += "camera_init_error=0x" + String((uint32_t)cameraInitError, HEX) + "\n";
    message += "capture_fail_count=" + String(captureFailCount) + "\n";
    server.send(500, "text/plain", message);
    return;
  }

  WiFiClient client = server.client();
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  client.write(fb->buf, fb->len);
  releaseFrame(fb);
}

static void sendCapture(framesize_t frameSize, const char *label, bool highResTiming) {
  camera_fb_t *fb = highResTiming
      ? captureFrameAdvanced(frameSize, 700, 4, 3)
      : captureFrame(frameSize);
  if (!fb) {
    String message = String(label) + " capture failed\n";
    message += "camera_ready=" + String(cameraReady ? "true" : "false") + "\n";
    message += "camera_init_error=0x" + String((uint32_t)cameraInitError, HEX) + "\n";
    message += "capture_fail_count=" + String(captureFailCount) + "\n";
    server.send(500, "text/plain", message);
    return;
  }

  WiFiClient client = server.client();
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  client.write(fb->buf, fb->len);
  releaseFrame(fb);
}

static void handleCaptureSvgaJpg() {
  sendCapture(CAMERA_SVGA_FRAME_SIZE, "SVGA", true);
}

static void handleCaptureXgaJpg() {
  sendCapture(CAMERA_XGA_FRAME_SIZE, "XGA", true);
}

static void handleCaptureSxgaJpg() {
  sendCapture(CAMERA_SXGA_FRAME_SIZE, "SXGA", true);
}

static void handleCaptureHighresJpg() {
  sendCapture(CAMERA_HIGHRES_FRAME_SIZE, "UXGA", true);
}

static void handleSpectrumJson() {
  SpectrumSample s = readSpectrum();
  server.send(200, "application/json", spectrumToJson(s));
}

static void handleStm32Json() {
  server.send(200, "application/json", stm32ToJson());
}

static void handleSccbScan() {
  server.send(200, "application/json", scanSccbToJson());
}

static void handleCameraId() {
  server.send(200, "application/json", cameraIdToJson());
}

static void handleSettingsJson() {
  String json = "{";
  json += "\"brightness\":" + String(cameraBrightness);
  json += ",\"manual_exposure\":" + String(manualExposure ? "true" : "false");
  json += ",\"aec_value\":" + String(cameraAecValue);
  json += ",\"agc_gain\":" + String(cameraAgcGain);
  json += ",\"stream_url\":\"http://192.168.4.1:" + String(CAMERA_STREAM_PORT) + "/stream\"";
  json += ",\"stream_frame\":\"QVGA\"";
  json += ",\"snapshot_frame\":\"VGA\"";
  json += "}";
  server.send(200, "application/json", json);
}

static void handleControl() {
  if (server.hasArg("brightness")) {
    cameraBrightness = clampInt(server.arg("brightness").toInt(), -2, 2);
    if (cameraMutex) {
      xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(1000));
    }
    sensor_t *sensor = esp_camera_sensor_get();
    applyCameraTuning(sensor);
    if (cameraMutex) {
      xSemaphoreGive(cameraMutex);
    }
  }

  handleSettingsJson();
}

static void handleExposure() {
  String mode = server.hasArg("mode") ? server.arg("mode") : "low";

  if (mode == "auto") {
    manualExposure = false;
  } else {
    manualExposure = true;
    if (mode == "low") {
      cameraAecValue = 80;
      cameraAgcGain = 1;
    } else if (mode == "mid") {
      cameraAecValue = 160;
      cameraAgcGain = 2;
    } else if (mode == "high") {
      cameraAecValue = 320;
      cameraAgcGain = 4;
    }

    if (server.hasArg("aec")) {
      cameraAecValue = clampInt(server.arg("aec").toInt(), 0, 1200);
    }
    if (server.hasArg("gain")) {
      cameraAgcGain = clampInt(server.arg("gain").toInt(), 0, 30);
    }
  }

  if (cameraMutex) {
    xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(1000));
  }
  applyCameraTuning(esp_camera_sensor_get());
  if (cameraMutex) {
    xSemaphoreGive(cameraMutex);
  }

  String json = "{";
  json += "\"ok\":true";
  json += ",\"manual\":" + String(manualExposure ? "true" : "false");
  json += ",\"aec_value\":" + String(cameraAecValue);
  json += ",\"agc_gain\":" + String(cameraAgcGain);
  json += "}";
  server.send(200, "application/json", json);
}

static void handleFlash() {
  if (server.hasArg("on")) {
    int value = server.arg("on").toInt();
    setCameraFlash(value != 0);
  }

  String json = "{";
  json += "\"ok\":true";
  json += ",\"flash_on\":" + String(cameraFlashOn ? "true" : "false");
  json += ",\"flash_pin\":" + String(CAMERA_FLASH_PIN);
  json += "}";
  server.send(200, "application/json", json);
}

static void handleDataJson() {
  SpectrumSample s = readSpectrum();
  String json = "{";
  json += "\"device\":\"esp32-s3-grape-detector\"";
  json += ",\"ip\":\"" + ipToString(WiFi.getMode() == WIFI_AP ? WiFi.softAPIP() : WiFi.localIP()) + "\"";
  json += ",\"spectrum\":" + spectrumToJson(s);
  json += ",\"stm32\":" + stm32ToJson();
  json += ",\"image_url\":\"/capture.jpg\"";
  json += "}";
  server.send(200, "application/json", json);
}

static void handleHealth() {
  String json = "{";
  json += "\"ok\":true";
  json += ",\"psram\":" + String(psramFound() ? "true" : "false");
  json += ",\"camera_ready\":" + String(cameraReady ? "true" : "false");
  json += ",\"camera_init_error\":\"0x" + String((uint32_t)cameraInitError, HEX) + "\"";
  json += ",\"capture_fail_count\":" + String(captureFailCount);
  json += ",\"camera_flash_on\":" + String(cameraFlashOn ? "true" : "false");
  json += ",\"camera_flash_pin\":" + String(CAMERA_FLASH_PIN);
  json += ",\"manual_exposure\":" + String(manualExposure ? "true" : "false");
  json += ",\"aec_value\":" + String(cameraAecValue);
  json += ",\"agc_gain\":" + String(cameraAgcGain);
  json += ",\"camera_pins\":{";
  json += "\"siod\":" + String(CAM_PIN_SIOD);
  json += ",\"sioc\":" + String(CAM_PIN_SIOC);
  json += ",\"xclk\":" + String(CAM_PIN_XCLK);
  json += ",\"pclk\":" + String(CAM_PIN_PCLK);
  json += ",\"vsync\":" + String(CAM_PIN_VSYNC);
  json += ",\"href\":" + String(CAM_PIN_HREF);
  json += ",\"d0\":" + String(CAM_PIN_D0);
  json += ",\"d1\":" + String(CAM_PIN_D1);
  json += ",\"d2\":" + String(CAM_PIN_D2);
  json += ",\"d3\":" + String(CAM_PIN_D3);
  json += ",\"d4\":" + String(CAM_PIN_D4);
  json += ",\"d5\":" + String(CAM_PIN_D5);
  json += ",\"d6\":" + String(CAM_PIN_D6);
  json += ",\"d7\":" + String(CAM_PIN_D7);
  json += ",\"reset\":" + String(CAM_PIN_RESET);
  json += ",\"pwdn\":" + String(CAM_PIN_PWDN);
  json += "}";
  json += ",\"free_heap\":" + String(ESP.getFreeHeap());
  json += "}";
  server.send(200, "application/json", json);
}

static void startWiFi() {
  if (String(WIFI_SSID).length() > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.printf("Connecting WiFi: %s", WIFI_SSID);
    for (int i = 0; i < 30 && WiFi.status() != WL_CONNECTED; i++) {
      delay(500);
      Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
      Serial.print("WiFi STA IP: ");
      Serial.println(WiFi.localIP());
      return;
    }
    Serial.println("WiFi STA failed, starting AP.");
  }

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  Serial.print("AP SSID: ");
  Serial.println(AP_SSID);
  Serial.print("AP password: ");
  Serial.println(AP_PASSWORD);
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());
}

static void streamClient(WiFiClient client) {
  client.setNoDelay(true);
  client.print("HTTP/1.1 200 OK\r\n");
  client.print("Content-Type: multipart/x-mixed-replace; boundary=frame\r\n");
  client.print("Cache-Control: no-cache\r\n");
  client.print("Connection: close\r\n\r\n");

  while (client.connected()) {
    camera_fb_t *fb = captureFrame(CAMERA_STREAM_FRAME_SIZE);
    if (!fb) {
      delay(80);
      continue;
    }

    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.print("Content-Length: ");
    client.print(fb->len);
    client.print("\r\n\r\n");
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    releaseFrame(fb);
    delay(CAMERA_STREAM_DELAY_MS);
  }

  client.stop();
}

static void streamTask(void *param) {
  (void)param;
  streamServer.begin();
  Serial.printf("MJPEG stream server started: http://192.168.4.1:%d/stream\r\n", CAMERA_STREAM_PORT);

  for (;;) {
    WiFiClient client = streamServer.available();
    if (client) {
      String request = client.readStringUntil('\n');
      if (request.indexOf("GET /stream") >= 0) {
        streamClient(client);
      } else {
        client.print("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
        client.stop();
      }
    }
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

static void startStreamServer() {
  xTaskCreatePinnedToCore(
    streamTask,
    "streamTask",
    8192,
    nullptr,
    1,
    nullptr,
    0
  );
}

static void startWebServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/live", HTTP_GET, handleLivePage);
  server.on("/capture.jpg", HTTP_GET, handleCaptureJpg);
  server.on("/capture-vga.jpg", HTTP_GET, handleCaptureVgaJpg);
  server.on("/capture-svga.jpg", HTTP_GET, handleCaptureSvgaJpg);
  server.on("/capture-xga.jpg", HTTP_GET, handleCaptureXgaJpg);
  server.on("/capture-sxga.jpg", HTTP_GET, handleCaptureSxgaJpg);
  server.on("/capture-uxga.jpg", HTTP_GET, handleCaptureHighresJpg);
  server.on("/spectrum.json", HTTP_GET, handleSpectrumJson);
  server.on("/stm32.json", HTTP_GET, handleStm32Json);
  server.on("/sccb-scan.json", HTTP_GET, handleSccbScan);
  server.on("/camera-id.json", HTTP_GET, handleCameraId);
  server.on("/settings.json", HTTP_GET, handleSettingsJson);
  server.on("/control", HTTP_GET, handleControl);
  server.on("/exposure", HTTP_GET, handleExposure);
  server.on("/flash", HTTP_GET, handleFlash);
  server.on("/data.json", HTTP_GET, handleDataJson);
  server.on("/health", HTTP_GET, handleHealth);
  server.begin();
  Serial.println("HTTP server started");
}

static void printHelp() {
  Serial.println();
  Serial.println("Commands:");
  Serial.println("  h = help");
  Serial.println("  s = read AS7341 spectrum as CSV");
  Serial.println("  j = read AS7341 spectrum as JSON");
  Serial.println("  c = capture one OV2640 frame test");
  Serial.println("  u = print latest STM32 UART line");
  Serial.println("  w = print WiFi address");
  Serial.println();
}

static void handleSerialCommand(char cmd) {
  if (cmd == '\r' || cmd == '\n' || cmd == ' ') {
    return;
  }

  switch (cmd) {
    case 'h':
    case 'H':
      printHelp();
      break;
    case 's':
    case 'S': {
      SpectrumSample s = readSpectrum();
      if (s.ok) {
        printSpectrumCsv(s);
      }
      break;
    }
    case 'j':
    case 'J': {
      SpectrumSample s = readSpectrum();
      Serial.println(spectrumToJson(s));
      break;
    }
    case 'c':
    case 'C':
      captureToSerial();
      break;
    case 'u':
    case 'U':
      Serial.println(stm32ToJson());
      break;
    case 'w':
    case 'W':
      if (WiFi.getMode() == WIFI_AP) {
        Serial.print("AP URL: http://");
        Serial.println(WiFi.softAPIP());
      } else {
        Serial.print("STA URL: http://");
        Serial.println(WiFi.localIP());
      }
      break;
    default:
      Serial.println("Unknown command. Type h.");
      break;
  }
}

static void initStm32Uart() {
  stm32Serial.begin(STM32_UART_BAUD, SERIAL_8N1, STM32_UART_RX_PIN, STM32_UART_TX_PIN);
  Serial.printf("STM32 UART started: TX=GPIO%d RX=GPIO%d baud=%d\r\n",
                STM32_UART_TX_PIN, STM32_UART_RX_PIN, STM32_UART_BAUD);
}

static void pollStm32Uart() {
  while (stm32Serial.available()) {
    char c = (char)stm32Serial.read();
    if (c == '\r') {
      continue;
    }
    if (c == '\n') {
      if (stm32LineBuffer.length() > 0) {
        lastStm32Line = stm32LineBuffer;
        lastStm32LineMs = millis();
        Serial.print("[STM32] ");
        Serial.println(lastStm32Line);
        stm32LineBuffer = "";
      }
      continue;
    }

    if (stm32LineBuffer.length() < 240) {
      stm32LineBuffer += c;
    } else {
      stm32LineBuffer = "";
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("Grape Quality Detector - ESP32-S3 + OV2640 + AS7341");
  cameraMutex = xSemaphoreCreateMutex();

#if WHITE_LED_PIN >= 0
  pinMode(WHITE_LED_PIN, OUTPUT);
  setWhiteLed(false);
#endif

#if CAMERA_FLASH_PIN >= 0
  pinMode(CAMERA_FLASH_PIN, OUTPUT);
  setCameraFlash(false);
#endif

  startWiFi();
  startWebServer();
  initStm32Uart();

  bool cameraOk = initCamera();
  as7341Ready = initAs7341();
  Serial.printf("Init summary: camera=%s, as7341=%s, psram=%s\r\n",
                cameraOk ? "OK" : "FAIL",
                as7341Ready ? "OK" : "DISABLED/FAIL",
                psramFound() ? "YES" : "NO");
  if (cameraOk) {
    startStreamServer();
  }

  printHelp();
}

void loop() {
  server.handleClient();
  pollStm32Uart();

  while (Serial.available()) {
    handleSerialCommand((char)Serial.read());
  }
}
