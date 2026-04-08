#ifndef LEDS_H
#define LEDS_H

#include <stdbool.h>
#include "coax.h"

#define PIN_LED_STS 26
#define PIN_LED_ERR 27

typedef struct {
    int pin_tx;
    int pin_rx;
} port_leds_t;

extern const port_leds_t port_leds[NUM_PORTS];

void leds_init(void);
void leds_startup_show(void);

// Call from main loop to update all timed LED state
void leds_update(void);

// Trigger TX activity LED for a port (stretched to 100ms minimum)
void led_tx_activity(int port);

// Update terminal-connected state for a port (affects RX LED)
void led_set_terminal_connected(int port, bool connected);

// STS LED
void led_set_sts(bool on);

#endif
