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
static bool programs_loaded;
static int release_depth;

static void claim_pio(void) {
    // Claim state machines
    rx_sm = pio_claim_unused_sm(RX_PIO, true);
    tx_sm = pio_claim_unused_sm(TX_PIO, true);
    tx_delay_sm = pio_claim_unused_sm(TX_PIO, true);

    // Load PIO programs
    rx_program_offset = pio_add_program(RX_PIO, &recv_serial_program);
    tx_program_offset = pio_add_program(TX_PIO, &xmit_serial_program);
    tx_delay_program_offset = pio_add_program(TX_PIO, &xmit_serial_delay_program);

    programs_loaded = true;
}

static void idle_port_pins(int port) {
    const coax_port_pins_t *p = &port_pins[port];
    const uint pins[] = { p->pin_tx, p->pin_tx_active, p->pin_tx_delay };

    for (int i = 0; i < 3; i++) {
        gpio_set_function(pins[i], GPIO_FUNC_SIO);
        gpio_set_dir(pins[i], GPIO_OUT);
        gpio_put(pins[i], 0);
    }
}

void coax_init(void) {
    claim_pio();

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

void coax_release(void) {
    if (release_depth++ > 0) return;
    if (!programs_loaded) return;

    pio_sm_set_enabled(RX_PIO, rx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_delay_sm, false);

    if (current_port >= 0) {
        idle_port_pins(current_port);
    }

    pio_remove_program(RX_PIO, &recv_serial_program, rx_program_offset);
    pio_remove_program(TX_PIO, &xmit_serial_program, tx_program_offset);
    pio_remove_program(TX_PIO, &xmit_serial_delay_program, tx_delay_program_offset);

    pio_sm_unclaim(RX_PIO, rx_sm);
    pio_sm_unclaim(TX_PIO, tx_sm);
    pio_sm_unclaim(TX_PIO, tx_delay_sm);

    programs_loaded = false;
    current_port = -1;
}

void coax_restore(void) {
    if (release_depth > 0 && --release_depth > 0) return;
    if (programs_loaded) return;

    claim_pio();
    coax_switch_port(0);
}

bool coax_available(void) {
    return programs_loaded;
}

void coax_switch_port(int port) {
    if (port < 0 || port >= NUM_PORTS) return;
    if (port == current_port) return;
    if (!programs_loaded) return;

    const coax_port_pins_t *p = &port_pins[port];

    // Disable all SMs
    pio_sm_set_enabled(RX_PIO, rx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_delay_sm, false);

    // If switching away from a port, return previous pins to GPIO
    if (current_port >= 0) {
        idle_port_pins(current_port);
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

// pio_sm_restart() resets the shift counters and the clock divider, but it
// leaves the program counter where the state machine was stopped and does not
// touch the FIFOs.  A transaction ends by disabling the state machines while
// they sit in the middle of their programs, so the next one has to send them
// back to the top and discard whatever the last one left behind.  This is the
// tail of pio_sm_init(), which runs only from coax_switch_port() and which
// that function skips when the port has not changed.
static void sm_reset(PIO pio, uint sm, uint program_offset) {
    pio_sm_set_enabled(pio, sm, false);
    pio_sm_clear_fifos(pio, sm);
    pio_sm_restart(pio, sm);
    pio_sm_clkdiv_restart(pio, sm);
    pio_sm_exec(pio, sm, pio_encode_jmp(program_offset));
}

// How long the transmit DMA is given to drain into the PIO. A full frame at
// the line rate is tens of milliseconds; anything beyond this is a state
// machine that has stopped consuming.
#define TX_DRAIN_TIMEOUT_MS 500

// Transaction buffers.  The receive buffer has one extra halfword for
// the end of frame marker (0xffff), the transmit buffer one extra word
// for the count that leads the frame.
static uint16_t rx_dma_buf[MAX_FRAME_LENGTH + 1];
static uint32_t tx_encoded[MAX_FRAME_LENGTH + 1];

// Number of halfwords the receive DMA has stored so far.
static int rx_dma_written(void) {
    uintptr_t next = dma_channel_hw_addr(rx_dma_chan)->write_addr;
    return (int)((next - (uintptr_t)rx_dma_buf) / sizeof(rx_dma_buf[0]));
}

static void setup_rx_dma(uint16_t *buf, int count) {
    // Reset before the DMA is armed, so that a word left in the RX FIFO by
    // the previous transaction is discarded instead of being transferred
    // into the fresh buffer.
    sm_reset(RX_PIO, rx_sm, rx_program_offset);

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

    pio_sm_set_enabled(RX_PIO, rx_sm, true);
}

static void setup_tx_dma(const uint32_t *buf, int count) {
    sm_reset(TX_PIO, tx_delay_sm, tx_delay_program_offset);
    sm_reset(TX_PIO, tx_sm, tx_program_offset);

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

    pio_sm_set_enabled(TX_PIO, tx_delay_sm, true);
    pio_sm_set_enabled(TX_PIO, tx_sm, true);
}

int coax_transact(const uint8_t *tx_words, int tx_word_count,
                  uint8_t *rx_buf, int rx_buf_size, int timeout_ms,
                  coax_timing_t *timing) {
    if (!programs_loaded) return COAX_ERROR;

    // Enforce minimum timeout
    if (timeout_ms < 5) timeout_ms = 5;

    if (timing) {
        timing->tx_start_us = time_us_64();
        timing->rx_end_us = timing->tx_start_us;
    }

    // Encode TX data
    int tx_count = coax_encode_tx_buf(tx_words, tx_word_count, tx_encoded,
                                       MAX_FRAME_LENGTH + 1);
    if (tx_count < 0) return COAX_ERROR;

    // Start DMA transfers
    const int rx_halfword_count = MAX_FRAME_LENGTH + 1;
    setup_rx_dma(rx_dma_buf, rx_halfword_count);
    if (timing) timing->tx_start_us = time_us_64();
    setup_tx_dma(tx_encoded, tx_count);

    // Wait for TX DMA to complete before starting the response timeout,
    // since large frames (e.g. 80x25 screen) take ~20ms to transmit.  The
    // wait is bounded: the PIO drains the buffer at the line rate, and a
    // state machine that has stopped consuming would otherwise hold this
    // loop -- and with it the whole main loop -- for as long as the
    // interface is powered, which reaches the host as an interface that has
    // gone silent rather than as a transaction that failed.
    absolute_time_t tx_deadline = make_timeout_time_ms(TX_DRAIN_TIMEOUT_MS);
    while (dma_channel_is_busy(tx_dma_chan)) {
        if (time_reached(tx_deadline)) {
            dma_channel_abort(tx_dma_chan);
            dma_channel_abort(rx_dma_chan);
            return COAX_ERROR;
        }
        tight_loop_contents();
    }

    // Now start the response timeout.  The DMA fills the buffer in order,
    // so only the words it has written since the last look need checking
    // for the end of frame marker.
    absolute_time_t deadline = make_timeout_time_ms(timeout_ms);
    int receive_count = -1;
    int scanned = 0;

    while (receive_count == -1 && !time_reached(deadline)) {
        int written = rx_dma_written();
        for (int i = scanned; i < written; i++) {
            if (rx_dma_buf[i] == 0xffff) {
                receive_count = i;
                break;
            }
        }
        scanned = written;
        if (receive_count == -1) {
            sleep_us(100);
        }
    }

    if (timing) timing->rx_end_us = time_us_64();

    // Disable state machines
    pio_sm_set_enabled(RX_PIO, rx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_sm, false);
    pio_sm_set_enabled(TX_PIO, tx_delay_sm, false);

    // Abort DMA
    dma_channel_abort(rx_dma_chan);
    dma_channel_abort(tx_dma_chan);

    int result = COAX_TIMEOUT;
    if (receive_count != -1) {
        // Copy received data to output buffer (as bytes, little-endian 16-bit words)
        int byte_count = receive_count * 2;
        if (byte_count > rx_buf_size) byte_count = rx_buf_size;
        memcpy(rx_buf, rx_dma_buf, byte_count);
        result = byte_count;
    }

    // Clear what this transaction stored, so the next one never mistakes
    // a leftover end marker for its own.
    int written = rx_dma_written();
    if (written > rx_halfword_count) written = rx_halfword_count;
    memset(rx_dma_buf, 0, written * sizeof(rx_dma_buf[0]));

    return result;
}
