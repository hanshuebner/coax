#include "pico/stdlib.h"
#include "tusb.h"
#include "leds.h"

const port_leds_t port_leds[NUM_PORTS] = {
    { .pin_tx =  8, .pin_rx =  7 },
    { .pin_tx = 13, .pin_rx = 22 },
    { .pin_tx =  1, .pin_rx =  0 },
    { .pin_tx = 28, .pin_rx =  6 },
};

// Sweep order matches physical LED positions on the board
static const int sweep_leds[] = { 8, 7, 13, 22, 1, 0, 28, 6 };
#define NUM_SWEEP_LEDS (sizeof(sweep_leds) / sizeof(sweep_leds[0]))

// All LEDs that need GPIO init
static const int all_leds[] = { 8, 7, 13, 22, 1, 0, 28, 6, 26, 27 };
#define NUM_ALL_LEDS (sizeof(all_leds) / sizeof(all_leds[0]))

// TX activity: time when LED should turn off
static absolute_time_t tx_off_time[NUM_PORTS];
static bool tx_led_on[NUM_PORTS];

// RX (CDC connected) blink state
static bool rx_led_on[NUM_PORTS];
static absolute_time_t rx_next_toggle[NUM_PORTS];

// STS blink state
static bool sts_on;
static absolute_time_t sts_next_toggle;

void leds_init(void) {
    for (int i = 0; i < (int)NUM_ALL_LEDS; i++) {
        gpio_init(all_leds[i]);
        gpio_set_dir(all_leds[i], GPIO_OUT);
        gpio_put(all_leds[i], 0);
    }

    for (int i = 0; i < NUM_PORTS; i++) {
        tx_led_on[i] = false;
        rx_led_on[i] = false;
        rx_next_toggle[i] = get_absolute_time();
    }

    sts_on = false;
    sts_next_toggle = get_absolute_time();
}

void leds_startup_show(void) {
    for (int i = 0; i < (int)NUM_SWEEP_LEDS; i++) {
        gpio_put(sweep_leds[i], 1);
        sleep_ms(30);
    }
    for (int i = 0; i < (int)NUM_SWEEP_LEDS; i++) {
        gpio_put(sweep_leds[i], 0);
        sleep_ms(30);
    }

    gpio_put(PIN_LED_ERR, 1);
    sleep_ms(500);
    gpio_put(PIN_LED_ERR, 0);
}

void led_tx_activity(int port) {
    if (port < 0 || port >= NUM_PORTS) return;
    gpio_put(port_leds[port].pin_tx, 1);
    tx_led_on[port] = true;
    tx_off_time[port] = make_timeout_time_ms(100);
}

void led_set_sts(bool on) {
    gpio_put(PIN_LED_STS, on);
}

void leds_update(void) {
    // TX activity LEDs: turn off after stretch period
    for (int i = 0; i < NUM_PORTS; i++) {
        if (tx_led_on[i] && time_reached(tx_off_time[i])) {
            gpio_put(port_leds[i].pin_tx, 0);
            tx_led_on[i] = false;
        }
    }

    // RX LEDs: solid on when CDC connected, off when not
    for (int i = 0; i < NUM_PORTS; i++) {
        bool connected = tud_cdc_n_connected(i);
        if (connected != rx_led_on[i]) {
            rx_led_on[i] = connected;
            gpio_put(port_leds[i].pin_rx, connected);
        }
    }

    // STS LED: 500ms on, 500ms off
    if (time_reached(sts_next_toggle)) {
        sts_on = !sts_on;
        gpio_put(PIN_LED_STS, sts_on);
        sts_next_toggle = make_timeout_time_ms(1000);
    }
}
