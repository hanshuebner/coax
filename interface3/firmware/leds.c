#include "pico/stdlib.h"
#include "leds.h"
#include "coax.h"

static const int all_leds[] = {
    8, 13, 1, 28,   // port activity LEDs
    26, 27,          // STS, ERR
};
#define NUM_LEDS (sizeof(all_leds) / sizeof(all_leds[0]))

void leds_init(void) {
    for (int i = 0; i < (int)NUM_LEDS; i++) {
        gpio_init(all_leds[i]);
        gpio_set_dir(all_leds[i], GPIO_OUT);
        gpio_put(all_leds[i], 0);
    }
}

void led_set(int pin, bool on) {
    gpio_put(pin, on);
}

void leds_startup_show(void) {
    for (int i = 0; i < (int)NUM_LEDS; i++) {
        gpio_put(all_leds[i], 1);
        sleep_ms(30);
    }
    for (int i = 0; i < (int)NUM_LEDS; i++) {
        gpio_put(all_leds[i], 0);
        sleep_ms(30);
    }
}
