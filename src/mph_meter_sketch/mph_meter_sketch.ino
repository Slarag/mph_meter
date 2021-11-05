//Includes
#include <LiquidCrystal.h>
#include <stdlib.h>
#include <EEPROM.h>

//version
#define VERSION "0.2"
#define AUTHOR "Michael Fiederer"

/*
 * changelog:
 *  v0.1:
 *    -initial release
 *  v0.2:
 *    -fixed type conversion error for muem_per_pulse and debonce_time_ms when receiving values from serial port
 *      (conversion from unsinged long to unsigned inta and back to unssigned long caused overruns)
 *    -fixed upper limit for muem_per_pulse (from 99,999,999 to 999,999,999)
 *    -fixed slow response at serial port by reducing delay in main function from 500 to 50ms
 *    -increased possible SW debounce time from 999ms to 999.999ms
 *    -first mph value calculation now happen with the second pulse, not directly with the first pulse to ommit incorect values
 * 
 */

//Pin definitions
#define input_pin 2

#define lcd_rs 13
#define lcd_en 12
#define lcd_d4 11
#define lcd_d5 10
#define lcd_d6 9
#define lcd_d7 8

#define bat_pin A0

//Constants
const char *greet_msgs[][2]= {
  {
    "    m/h Meter   ",
    "",
  },
  {
    "   written by   ",
    AUTHOR,
  }
};
const int msg_count = 2;
const int disp_time_ms = 1000;

//Struct for Data stored in EEPROM
struct eepdata{
  unsigned long muem_per_pulse;
  unsigned long debounce_time_ms;
  unsigned long bat_critical_mv;
};

//Instance of variables
eepdata stored_vars;

//Count loop cycles to update display only every tenth cycle (see explanation in function below)
int counter = 0;

//Variables used for mph calculation
volatile unsigned long last_pulse = 0UL;
volatile unsigned long last_pulse_interval = 0UL;

//Serial rx bufer definiation
const size_t serial_rx_size = 12;
char serial_rx_buf[12];
size_t serial_rx_pos = 0;

//LCD
LiquidCrystal lcd(lcd_rs, lcd_en, lcd_d4, lcd_d5, lcd_d6, lcd_d7);

void setup() {
  //serial port for communication with Configuration tool
  Serial.begin(9600);

  //Clear rx buffer
  memset(serial_rx_buf, 0, serial_rx_size);

  //read values stored in EEPROM
  EEPROM.get(0, stored_vars);
  
  //External pullup is used
  pinMode(input_pin, INPUT);

  //add interupt handler
  attachInterrupt(digitalPinToInterrupt(input_pin), on_meas, RISING);
  
  greet();
  warn_on_vbat_low(read_vbat());

  //Setup main display
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(" Meter per hour ");
}

void loop() {
  //Calculate and update mph value on screen every 50ms
  char mphstr[12];

  //Update display only every tenth loop cycle (otherwise the values become unreadable when calculating value down
  //The short delay of only 50ms is needed as Arduino is shit an will only call SerialEvent only once before/after/whatever each time loop runs. Otherwise the serial port communication is a mess.
  if (counter == 10) {
    lcd.setCursor(0, 1);
    dtostrf(calc_mph(), 12, 2, mphstr);
    lcd.print(mphstr);
    lcd.print(" mph");
    counter = 0;
  }
  else {
    counter++;
  } 
  delay(50);

}

void serialEvent() {
  //Write data received from UART into buffer and eveluate command when \n was received
    while(Serial.available()){
        serial_rx_buf[serial_rx_pos] = (char)Serial.read();

        if (serial_rx_buf[serial_rx_pos] == '\n'){
            if (serial_rx_buf[0] == 'r'){
              //read command
              //dump data over UART
                char buff [50];
                sprintf(buff, "%lu;%lu;%s;%lu;%lu\n", stored_vars.muem_per_pulse, stored_vars.debounce_time_ms, VERSION, stored_vars.bat_critical_mv, (unsigned long)(read_vbat()*1000));
                Serial.write(buff);
             }
            else if (serial_rx_buf[0] == 'm'){
              //change muem_per_pulse value, update EEPROM
                unsigned long value = strtoul(&serial_rx_buf[1], NULL, 10);
                if (value > 999999999){
                  Serial.write("ERR\n");
                }
                else {
                  stored_vars.muem_per_pulse = value;
                  EEPROM.put(0, stored_vars);
                  Serial.write("OK\n");
                }
            }
            else if (serial_rx_buf[0] == 'd'){
              //change debounce_time_ms value, update EEPROM
                unsigned long value = strtoul(&serial_rx_buf[1], NULL, 10);
                if (value > 999999){
                  Serial.write("ERR\n");
                }
                else {
                  stored_vars.debounce_time_ms = strtoul(&serial_rx_buf[1], NULL, 10);
                  EEPROM.put(0, stored_vars);
                  Serial.write("OK\n");
                }
            }
            else if (serial_rx_buf[0] == 't'){
              //change bat_critical_mv value, update EEPROM
                unsigned long value = strtoul(&serial_rx_buf[1], NULL, 10);
                if (value > 15000){
                  Serial.write("ERR\n");
                }
                else {
                  stored_vars.bat_critical_mv = strtoul(&serial_rx_buf[1], NULL, 10);
                  EEPROM.put(0, stored_vars);
                  Serial.write("OK\n");
                }
            }
            else if (serial_rx_buf[0] == 'i'){
              //identify command. Write "mph Meter\n" to UART
                Serial.write("mph Meter\n");
            }
            else {
              //Sennd error message if no valid command was parsed
              Serial.write("ERR\n");
            }
            //Clear buffer after command was evaluated
            serial_rx_pos = 0;
            memset(serial_rx_buf, 0, serial_rx_size);
            
        }
        //Clear buffer if it is full and send error message
        if (serial_rx_pos >= serial_rx_size)
        {
            serial_rx_pos = 0;
            memset(serial_rx_buf, 0, serial_rx_size);
            Serial.write("ERR\n");
        }
        //Increase buffer write position if buffer was not cleared previously
        if (serial_rx_buf[serial_rx_pos] != 0) {
          serial_rx_pos++;
        }
    }
}

void greet() {
  /*
  Display startup message
  */
    
  //iterate through greet_msgs and display strings on LCD
  lcd.begin(16, 2);
  for (size_t i=0; i<msg_count; i++){
    for (size_t y=0; y<2; y++){
      lcd.setCursor(0,y);
      lcd.print(greet_msgs[i][y]);
    }
  delay(disp_time_ms);
  }
}

void on_meas() {
  /*
  Interrupt handler. Called at every pulse on input pin (pin is debounce at hardware side to minimize interrupts)
  Get timedelta since last pulse
  */
  unsigned long now = millis();

  //Calculate timedelta since last pulse
  //Additional Software debouncing if required
  if (now > last_pulse + stored_vars.debounce_time_ms) {
    if ((last_pulse != 0UL)){
      last_pulse_interval = now - last_pulse;
    }
    last_pulse = now;
  }
}

double read_vbat() {
  /*
  Measure supply voltage
  */
  
  //initial read might be inacurate, so just ignore it
  analogRead(bat_pin);
  return (10.0 * double(analogRead(bat_pin)) / 1024.0);
}

void warn_on_vbat_low(float voltage){
  //Display warning on LCD if battery is low
  char vbatstr[14];
  if (voltage <= float(stored_vars.bat_critical_mv)/1000) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("  Battery low!  ");
    lcd.setCursor(0, 1);
    dtostrf(voltage, 14, 2, vbatstr);
    lcd.print(vbatstr);
    lcd.print(" V");
    delay(1000);
  }
}

double calc_mph() {
  /*
  Calc mph value
  */
  unsigned long time_since_pulse = millis() - last_pulse;

  //Automatically downscale mph value if last pulse too long ago
  if (time_since_pulse > last_pulse_interval and last_pulse_interval != 0) {
    last_pulse_interval = time_since_pulse;
  }
  
  //Calculate mph
  if (last_pulse_interval != 0) {
    return (double)(stored_vars.muem_per_pulse * 36UL) / (float)(10UL * last_pulse_interval);
  }

  return 0.0;
}
