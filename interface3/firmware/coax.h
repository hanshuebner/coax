#ifndef COAX_H
#define COAX_H

#include <stdint.h>
#include <stdbool.h>

#define NUM_PORTS 4

#define BIT_RATE 2358700
#define PIO_FREQ (12 * BIT_RATE)

#define MAX_FRAME_LENGTH (80 * 25 + 16)

// Per-port pin configuration
typedef struct {
    uint pin_rx;
    uint pin_tx;
    uint pin_tx_active;
    uint pin_tx_delay;
    uint pin_led;
} coax_port_pins_t;

extern const coax_port_pins_t port_pins[NUM_PORTS];

// Error codes
#define COAX_OK          0
#define COAX_TIMEOUT    -1
#define COAX_ERROR      -2

void coax_init(void);
void coax_switch_port(int port);
uint32_t coax_manchester_encode(uint16_t value);
int coax_encode_tx_buf(const uint8_t *words, int word_count, uint32_t *encoded, int encoded_size);
int coax_transact(const uint8_t *tx_words, int tx_word_count,
                  uint8_t *rx_buf, int rx_buf_size, int timeout_ms);

#endif
