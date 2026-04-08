#include <string.h>
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/dma.h"
#include "hardware/clocks.h"

#include "coax.h"
#include "coax.pio.h"

// Port pin assignments
const coax_port_pins_t port_pins[NUM_PORTS] = {
    { .pin_rx =  2, .pin_tx =  3, .pin_tx_active =  4, .pin_tx_delay =  5 },
    { .pin_rx =  9, .pin_tx = 10, .pin_tx_active = 11, .pin_tx_delay = 12 },
    { .pin_rx = 14, .pin_tx = 15, .pin_tx_active = 16, .pin_tx_delay = 17 },
    { .pin_rx = 18, .pin_tx = 19, .pin_tx_active = 20, .pin_tx_delay = 21 },
};

// recv_serial has set pin instructions for debug, but those GPIOs are now
// used for LEDs.  We keep set_count=0 so the instructions are harmless no-ops.

// PIO and SM assignments
#define RX_PIO  pio0
#define TX_PIO  pio1

static uint rx_sm;
static uint tx_sm;
static uint tx_delay_sm;

static uint rx_program_offset;
static uint tx_program_offset;
static uint tx_delay_program_offset;

static int tx_dma_chan;
static int rx_dma_chan;

static int current_port = -1;

void coax_init(void) {
    // Claim state machines
    rx_sm = pio_claim_unused_sm(RX_PIO, true);
    tx_sm = pio_claim_unused_sm(TX_PIO, true);
    tx_delay_sm = pio_claim_unused_sm(TX_PIO, true);

    // Load PIO programs
    rx_program_offset = pio_add_program(RX_PIO, &recv_serial_program);
    tx_program_offset = pio_add_program(TX_PIO, &xmit_serial_program);
    tx_delay_program_offset = pio_add_program(TX_PIO, &xmit_serial_delay_program);

    // Claim DMA channels
    tx_dma_chan = dma_claim_unused_channel(true);
    rx_dma_chan = dma_claim_unused_channel(true);

    // Initialize all port pins
    for (int i = 0; i < NUM_PORTS; i++) {
        const coax_port_pins_t *p = &port_pins[i];

        // RX pin — input
        gpio_init(p->pin_rx);
        gpio_set_dir(p->pin_rx, GPIO_IN);

        // TX pin — output, active low
        gpio_init(p->pin_tx);
        gpio_set_dir(p->pin_tx, GPIO_OUT);
        gpio_put(p->pin_tx, 0);

        // TX_ACTIVE — output
        gpio_init(p->pin_tx_active);
        gpio_set_dir(p->pin_tx_active, GPIO_OUT);
        gpio_put(p->pin_tx_active, 0);

        // TX_DELAY — output
        gpio_init(p->pin_tx_delay);
        gpio_set_dir(p->pin_tx_delay, GPIO_OUT);
        gpio_put(p->pin_tx_delay, 0);
    }

    // Configure port 0 as default
    coax_switch_port(0);
}

void coax_switch_port(int port) {
    if (port < 0 || port >= NUM_PORTS) return;
    if (port == current_port) return;

    const coax_port_pins_t *p = &port_pins[port];

    // Disable all SMs
    pio_sm_set_enabled(RX_PIO, rx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_delay_sm, false);

    // If switching away from a port, return previous pins to GPIO
    if (current_port >= 0) {
        const coax_port_pins_t *prev = &port_pins[current_port];
        gpio_set_function(prev->pin_tx, GPIO_FUNC_SIO);
        gpio_set_dir(prev->pin_tx, GPIO_OUT);
        gpio_put(prev->pin_tx, 0);

        gpio_set_function(prev->pin_tx_active, GPIO_FUNC_SIO);
        gpio_set_dir(prev->pin_tx_active, GPIO_OUT);
        gpio_put(prev->pin_tx_active, 0);

        gpio_set_function(prev->pin_tx_delay, GPIO_FUNC_SIO);
        gpio_set_dir(prev->pin_tx_delay, GPIO_OUT);
        gpio_put(prev->pin_tx_delay, 0);
    }

    // Configure recv_serial (RX) SM
    {
        pio_sm_config c = recv_serial_program_get_default_config(rx_program_offset);
        sm_config_set_in_shift(&c, false, true, 10);  // shift left, autopush at 10 bits
        sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_RX);
        sm_config_set_in_pins(&c, p->pin_rx);
        sm_config_set_jmp_pin(&c, p->pin_rx);
        sm_config_set_set_pins(&c, 0, 0);  // disable set pins (used for debug only)
        float div = (float)clock_get_hz(clk_sys) / PIO_FREQ;
        sm_config_set_clkdiv(&c, div);

        pio_sm_set_consecutive_pindirs(RX_PIO, rx_sm, p->pin_rx, 1, false);

        pio_sm_init(RX_PIO, rx_sm, rx_program_offset, &c);
    }

    // Configure xmit_serial (TX) SM
    {
        pio_sm_config c = xmit_serial_program_get_default_config(tx_program_offset);
        sm_config_set_out_shift(&c, false, false, 32);  // shift left, no autopull
        sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
        sm_config_set_out_pins(&c, p->pin_tx, 1);
        sm_config_set_set_pins(&c, p->pin_tx, 2);  // TX and TX_ACTIVE
        float div = (float)clock_get_hz(clk_sys) / PIO_FREQ;
        sm_config_set_clkdiv(&c, div);

        // Connect TX and TX_ACTIVE pins to PIO and set as outputs
        pio_gpio_init(TX_PIO, p->pin_tx);
        pio_gpio_init(TX_PIO, p->pin_tx_active);
        pio_sm_set_consecutive_pindirs(TX_PIO, tx_sm, p->pin_tx, 2, true);

        pio_sm_init(TX_PIO, tx_sm, tx_program_offset, &c);
    }

    // Configure xmit_serial_delay SM
    {
        pio_sm_config c = xmit_serial_delay_program_get_default_config(tx_delay_program_offset);
        sm_config_set_in_pins(&c, p->pin_tx);
        sm_config_set_set_pins(&c, p->pin_tx_delay, 1);
        float div = (float)clock_get_hz(clk_sys) / PIO_FREQ;
        sm_config_set_clkdiv(&c, div);

        // Connect TX_DELAY pin to PIO and set as output
        pio_gpio_init(TX_PIO, p->pin_tx_delay);
        pio_sm_set_consecutive_pindirs(TX_PIO, tx_delay_sm, p->pin_tx_delay, 1, true);

        pio_sm_init(TX_PIO, tx_delay_sm, tx_delay_program_offset, &c);
    }

    current_port = port;
}

uint32_t coax_manchester_encode(uint16_t value) {
    uint32_t parity = 1;
    uint32_t encoded = 0b10;  // start bit

    for (int i = 9; i >= 0; i--) {
        encoded <<= 2;
        if (value & (1 << i)) {
            encoded |= 0b10;
            parity++;
        } else {
            encoded |= 0b01;
        }
    }

    // Parity bit
    encoded <<= 2;
    if (parity & 1) {
        encoded |= 0b10;
    } else {
        encoded |= 0b01;
    }

    // Pad 8 bits to the right
    encoded <<= 8;
    return encoded;
}

int coax_encode_tx_buf(const uint8_t *words, int word_count,
                       uint32_t *encoded, int encoded_size) {
    int n_words = word_count / 2;
    int needed = n_words + 1;  // count word + encoded words
    if (needed > encoded_size) return -1;

    // First word: number of words - 1
    encoded[0] = (uint32_t)(n_words - 1);

    for (int i = 0; i < n_words; i++) {
        uint16_t w = (uint16_t)words[i * 2] | ((uint16_t)words[i * 2 + 1] << 8);
        encoded[i + 1] = coax_manchester_encode(w);
    }

    return needed;
}

static void setup_rx_dma(uint16_t *buf, int count) {
    dma_channel_config c = dma_channel_get_default_config(rx_dma_chan);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_16);
    channel_config_set_read_increment(&c, false);
    channel_config_set_write_increment(&c, true);
    channel_config_set_dreq(&c, pio_get_dreq(RX_PIO, rx_sm, false));

    dma_channel_configure(rx_dma_chan, &c,
        buf,                              // write address
        &RX_PIO->rxf[rx_sm],             // read address (PIO RX FIFO)
        count,                            // transfer count
        true);                            // start immediately

    pio_sm_restart(RX_PIO, rx_sm);
    pio_sm_set_enabled(RX_PIO, rx_sm, true);
}

static void setup_tx_dma(const uint32_t *buf, int count) {
    dma_channel_config c = dma_channel_get_default_config(tx_dma_chan);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_dreq(&c, pio_get_dreq(TX_PIO, tx_sm, true));

    dma_channel_configure(tx_dma_chan, &c,
        &TX_PIO->txf[tx_sm],             // write address (PIO TX FIFO)
        buf,                              // read address
        count,                            // transfer count
        true);                            // start immediately

    pio_sm_restart(TX_PIO, tx_delay_sm);
    pio_sm_set_enabled(TX_PIO, tx_delay_sm, true);
    pio_sm_restart(TX_PIO, tx_sm);
    pio_sm_set_enabled(TX_PIO, tx_sm, true);
}

int coax_transact(const uint8_t *tx_words, int tx_word_count,
                  uint8_t *rx_buf, int rx_buf_size, int timeout_ms) {
    // Enforce minimum timeout
    if (timeout_ms < 5) timeout_ms = 5;

    // Encode TX data
    int n_words = tx_word_count / 2;
    uint32_t tx_encoded[n_words + 1];
    int tx_count = coax_encode_tx_buf(tx_words, tx_word_count, tx_encoded,
                                       n_words + 1);
    if (tx_count < 0) return COAX_ERROR;

    // Set up RX buffer — one extra 16-bit word for end marker (0xffff)
    int rx_halfword_count = MAX_FRAME_LENGTH + 1;
    uint16_t rx_dma_buf[rx_halfword_count];
    memset(rx_dma_buf, 0, sizeof(rx_dma_buf));

    // Start DMA transfers
    setup_rx_dma(rx_dma_buf, rx_halfword_count);
    setup_tx_dma(tx_encoded, tx_count);

    // Wait for TX DMA to complete before starting the response timeout,
    // since large frames (e.g. 80x25 screen) take ~20ms to transmit.
    while (dma_channel_is_busy(tx_dma_chan)) {
        tight_loop_contents();
    }

    // Now start the response timeout
    absolute_time_t deadline = make_timeout_time_ms(timeout_ms);
    int receive_count = -1;

    while (receive_count == -1 && !time_reached(deadline)) {
        for (int i = 0; i < MAX_FRAME_LENGTH; i++) {
            if (rx_dma_buf[i] == 0xffff) {
                receive_count = i;
                break;
            }
        }
        if (receive_count == -1) {
            sleep_us(100);
        }
    }

    // Disable state machines
    pio_sm_set_enabled(RX_PIO, rx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_delay_sm, false);

    // Abort DMA
    dma_channel_abort(rx_dma_chan);
    dma_channel_abort(tx_dma_chan);

    if (receive_count == -1) {
        return COAX_TIMEOUT;
    }

    // Copy received data to output buffer (as bytes, little-endian 16-bit words)
    int byte_count = receive_count * 2;
    if (byte_count > rx_buf_size) byte_count = rx_buf_size;
    memcpy(rx_buf, rx_dma_buf, byte_count);

    return byte_count;
}
