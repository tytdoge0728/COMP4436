//IR sensor
#include <ArduinoJson.h> 
// Defining ports for LED.
#define RED 13
#define GRN 27
#define BLUE 2
// Defining ports for IR sensor
#define IR  5
#include <Wire.h>

// LCD display
#include <LiquidCrystal_I2C.h>
LiquidCrystal_I2C lcd(0x27,16,2); 
#define I2C_SDA 21
#define I2C_SCL 22

// wifi mttq
#include <WiFi.h>
#include <HTTPClient.h>
// Entry your wifi connection data
const char ssid[]="SID"; //SID
const char pwd[]="Password"; //Password

int ParkingST;

String url = "https://api.thingspeak.com/update?api_key=8WV6WWBIIDQTO3OP";

void setup() {
  Serial.begin(115200);
  lcd.clear();
  pinMode(IR, INPUT_PULLUP); //IR detection pin
  //Set up the LEDs
  pinMode(RED,OUTPUT);pinMode(GRN,OUTPUT);pinMode(BLUE,OUTPUT);
  digitalWrite(RED,HIGH);digitalWrite(GRN,HIGH);digitalWrite(BLUE,HIGH); // turn off all LEDs
  Wire.begin(I2C_SDA, I2C_SCL, 100000);
  lcd.begin();

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid,pwd); 
  Serial.print("WiFi connecting");

  while(WiFi.status()!=WL_CONNECTED){
    Serial.print(".");
    delay(500);   
  }
  Serial.println("");
  Serial.print("IP address:");
  Serial.println(WiFi.localIP()); //Read IP address
  Serial.print("WiFi RSSI:");
  Serial.println(WiFi.RSSI()); //Read WiFi strength

}


void UploadData(){
  HTTPClient http;
  String url1= url+"&field1="+(int)ParkingST;
  http.begin(url1);

  int httpCode = http.GET();
  if(httpCode == HTTP_CODE_OK){
    String payload = http.getString();
    Serial.print("Web_Output=");
    Serial.println(payload);
  }
  else{
     Serial.println("Transmission failed");
  }
  http.end(); 
}


int Count=0 ;

void loop() {
  int logic = digitalRead(IR);
  if (Count == 30){ // Upload data every 30 seconds.
    UploadData();
    Count = 0;
  }
  else{
    if (logic == 1) {
      lcd.clear();
      digitalWrite(RED,HIGH);digitalWrite(GRN,LOW);digitalWrite(BLUE,HIGH);
      Serial.println("No object");
      lcd.setCursor(0,0);
      lcd.print("Free");
      ParkingST = 0; 
    }
    else {
      lcd.clear();
      digitalWrite(RED,LOW);digitalWrite(GRN,HIGH);digitalWrite(BLUE,HIGH);
      Serial.println("Object detected");
      lcd.setCursor(0,0);
      lcd.print("Car Parking");
      ParkingST = 1;  
    }
    delay(1000); //Detection data every second
    Count++;
  }
}


