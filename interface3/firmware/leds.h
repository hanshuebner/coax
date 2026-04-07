#ifndef LEDS_H
#define LEDS_H

#include <stdbool.h>

#define PIN_LED_STS 26
#define PIN_LED_ERR 27

void leds_init(void);
void led_set(int pin, bool on);
void leds_startup_show(void);

#endif
