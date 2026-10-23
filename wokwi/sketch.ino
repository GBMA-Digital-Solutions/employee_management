#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>
#include <time.h>
#include "secrets.h"

constexpr uint8_t RELAY_PIN = 23;
constexpr bool RELAY_ACTIVE_LOW = true;
constexpr uint32_t POLL_MS = 400;
constexpr uint32_t UNLOCK_MS = 5000;
constexpr uint32_t RESYNC_MS = 600000;
bool unlocking = false;
uint32_t relockAt = 0;
String activeCommand;

void setLocked(bool locked) { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? (locked ? HIGH : LOW) : (locked ? LOW : HIGH)); }
String hexBytes(const uint8_t *data, size_t length) { const char *hex="0123456789abcdef"; String out; out.reserve(length*2); for(size_t i=0;i<length;i++){out+=hex[data[i]>>4];out+=hex[data[i]&15];} return out; }
String sha256(const String &value) { uint8_t digest[32]; mbedtls_sha256_ret((const unsigned char*)value.c_str(),value.length(),digest,0); return hexBytes(digest,32); }
String signature(const String &method,const String &path,const String &timestamp,const String &nonce,const String &body) {
  String canonical=method+"\n"+path+"\n"+timestamp+"\n"+nonce+"\n"+sha256(body);
  uint8_t key[32],digest[32]; mbedtls_sha256_ret((const unsigned char*)DOOR_DEVICE_SECRET,strlen(DOOR_DEVICE_SECRET),key,0);
  mbedtls_md_context_t ctx; mbedtls_md_init(&ctx); const mbedtls_md_info_t *info=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_setup(&ctx,info,1); mbedtls_md_hmac_starts(&ctx,key,32); mbedtls_md_hmac_update(&ctx,(const unsigned char*)canonical.c_str(),canonical.length()); mbedtls_md_hmac_finish(&ctx,digest); mbedtls_md_free(&ctx);
  return hexBytes(digest,32);
}
int signedPost(const String &path,const String &body,String &response) {
  HTTPClient http; String timestamp=String(time(nullptr)); String nonce=String(esp_random(),HEX)+String(esp_random(),HEX);
  http.begin(String(DJANGO_BASE_URL)+path); http.addHeader("Content-Type","application/json"); http.addHeader("X-Door-Timestamp",timestamp); http.addHeader("X-Door-Nonce",nonce); http.addHeader("X-Door-Signature",signature("POST",path,timestamp,nonce,body));
  int code=http.POST(body); response=code>0?http.getString():""; http.end(); return code;
}
void acknowledge(const String &command,const char *state) { String path="/api/door-devices/"+String(DOOR_DEVICE_ID)+"/commands/"+command+"/ack/"; String body=String("{\"status\":\"")+state+"\"}"; String response; int code=signedPost(path,body,response); Serial.printf("ACK %s -> HTTP %d %s\n",state,code,response.c_str()); }
void pollDoor() {
  String path="/api/door-devices/"+String(DOOR_DEVICE_ID)+"/poll/",response; int code=signedPost(path,"{}",response);
  if(code!=200){Serial.printf("Poll HTTP %d %.120s\n",code,response.c_str());return;} JsonDocument doc; if(deserializeJson(doc,response)||doc["command"].isNull())return;
  String id=doc["command"]["id"].as<String>(); if(unlocking||id==activeCommand||doc["command"]["relay_gpio"].as<int>()!=RELAY_PIN)return;
  activeCommand=id; unlocking=true; setLocked(false); relockAt=millis()+UNLOCK_MS; acknowledge(activeCommand,"executing"); Serial.println("Door unlocked; maglock LED OFF");
}
void setup() {
  Serial.begin(115200); pinMode(RELAY_PIN,OUTPUT); setLocked(true);
  WiFi.begin("Wokwi-GUEST","",6); while(WiFi.status()!=WL_CONNECTED){delay(100);}
  configTime(0,0,"pool.ntp.org"); while(time(nullptr)<1700000000){delay(100);}
  Serial.println("ESP32 online; maglock LED ON (locked)");
}
void loop() {
  if(unlocking&&(int32_t)(millis()-relockAt)>=0){setLocked(true);unlocking=false;acknowledge(activeCommand,"completed");Serial.println("Door relocked; maglock LED ON");}
  static uint32_t nextSync=RESYNC_MS; if((int32_t)(millis()-nextSync)>=0){configTime(0,0,"pool.ntp.org");nextSync=millis()+RESYNC_MS;}
  static uint32_t nextPoll=0; if(!unlocking&&(int32_t)(millis()-nextPoll)>=0){pollDoor();nextPoll=millis()+POLL_MS;} delay(10);
}
