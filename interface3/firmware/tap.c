#include <string.h>

#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/dma.h"
#include "hardware/clocks.h"

#include "tap.h"
#include "capture.h"
#include "coax.h"
#include "coax.pio.h"

// A chip with a spare PIO block listens alongside normal operation.  With
// two blocks the transmit and receive programs fill both, so the tap takes
// the receive program's place.
#if NUM_PIOS > 2
#define TAP_PIO      pio2
#define TAP_TAKES_RX 0
#else
#define TAP_PIO      pio0
#define TAP_TAKES_RX 1
#endif

// Words decoded by the state machine land here.  The DMA wraps within the
// ring on its own, which needs a power of two size and matching alignment.
#define RING_WORDS 4096
#define RING_BYTES (RING_WORDS * 2)
#define RING_BITS  13

static uint16_t ring[RING_WORDS] __attribute__((aligned(RING_BYTES)));
static uint32_t ring_read;

static int current_port = -1;
static uint tap_sm;
static uint tap_offset;
static int tap_dma = -1;

// The frame being assembled, and the poll held back to see whether the
// terminal answers it with anything worth recording.  Frames are stamped
// when the main loop reads their end marker out of the ring, so the times
// carry the latency of one pass through the loop.
static uint16_t frame[MAX_FRAME_LENGTH];
static int frame_len;

static bool poll_pending;
static uint16_t poll_word;
static uint64_t poll_us;

// A poll and the answer to it arrive as two frames a few hundred
// microseconds apart.
#define POLL_PAIR_TIMEOUT_US 2000

static void start_dma(void) {
    dma_channel_config c = dma_channel_get_default_config(tap_dma);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_16);
    channel_config_set_read_increment(&c, false);
    channel_config_set_write_increment(&c, true);
    channel_config_set_ring(&c, true, RING_BITS);
    channel_config_set_dreq(&c, pio_get_dreq(TAP_PIO, tap_sm, false));

    dma_channel_configure(tap_dma, &c,
        ring,                          // write address, wrapping in the ring
        &TAP_PIO->rxf[tap_sm],         // read address (PIO RX FIFO)
        0xffffffff,                    // run until stopped
        true);

    ring_read = 0;
}

static uint32_t dma_write_index(void) {
    uintptr_t addr = (uintptr_t)dma_channel_hw_addr(tap_dma)->write_addr;
    return (uint32_t)((addr - (uintptr_t)ring) / 2) & (RING_WORDS - 1);
}

static void emit(const uint16_t *words, int count, uint8_t extra_flags, uint64_t ts_us) {
    uint8_t flags = CAPTURE_FLAG_INFERRED | extra_flags;

    // Only a controller sends command words, so the first word tells the
    // two ends of the line apart.
    if (count > 0 && (words[0] & 1) == 0) {
        flags |= CAPTURE_FLAG_FROM_TERMINAL;
    }

    capture_frame(current_port, flags, (const uint8_t *)words, count, ts_us);
}

static void flush_poll(void) {
    if (!poll_pending) return;
    poll_pending = false;
    emit(&poll_word, 1, 0, poll_us);
}

static bool is_poll_word(uint16_t word) {
    // Command word, command bits holding POLL
    return (word & 1) == 1 && ((word >> 2) & 0x1f) == 0x01;
}

static void frame_complete(uint8_t extra_flags) {
    if (frame_len == 0) return;

    uint64_t now = time_us_64();

    // A poll answered by 0x0000 leaves the terminal state unchanged, so
    // the pair is left out unless idle polls were asked for.
    if (poll_pending && frame_len == 1 && frame[0] == 0x0000
        && now - poll_us < POLL_PAIR_TIMEOUT_US) {
        poll_pending = false;
        if (capture_wants_idle_polls(current_port)) {
            emit(&poll_word, 1, 0, poll_us);
            emit(frame, 1, 0, now);
        } else {
            capture_count_idle_poll(current_port);
        }
        frame_len = 0;
        return;
    }

    flush_poll();

    if (frame_len == 1 && is_poll_word(frame[0]) && extra_flags == 0) {
        // Hold it back until the answer is known.
        poll_pending = true;
        poll_word = frame[0];
        poll_us = now;
        frame_len = 0;
        return;
    }

    emit(frame, frame_len, extra_flags, now);
    frame_len = 0;
}

bool tap_start(int port) {
    if (port < 0 || port >= NUM_PORTS) return false;
    if (port == current_port) return true;

    tap_stop();

#if TAP_TAKES_RX
    coax_release();
#endif

    if (!pio_can_add_program(TAP_PIO, &recv_tap_program)) {
#if TAP_TAKES_RX
        coax_restore();
#endif
        return false;
    }

    tap_offset = pio_add_program(TAP_PIO, &recv_tap_program);
    tap_sm = pio_claim_unused_sm(TAP_PIO, true);
    if (tap_dma < 0) {
        tap_dma = dma_claim_unused_channel(true);
    }

    const coax_port_pins_t *p = &port_pins[port];
    gpio_init(p->pin_rx);
    gpio_set_dir(p->pin_rx, GPIO_IN);

    pio_sm_config c = recv_tap_program_get_default_config(tap_offset);
    sm_config_set_in_shift(&c, false, true, 10);  // shift left, autopush at 10 bits
    sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_RX);
    sm_config_set_in_pins(&c, p->pin_rx);
    sm_config_set_jmp_pin(&c, p->pin_rx);
    sm_config_set_set_pins(&c, 0, 0);  // disable set pins (used for debug only)
    sm_config_set_clkdiv(&c, (float)clock_get_hz(clk_sys) / PIO_FREQ);

    pio_sm_set_consecutive_pindirs(TAP_PIO, tap_sm, p->pin_rx, 1, false);
    pio_sm_init(TAP_PIO, tap_sm, tap_offset, &c);

    current_port = port;
    frame_len = 0;
    poll_pending = false;

    start_dma();
    pio_sm_set_enabled(TAP_PIO, tap_sm, true);

    return true;
}

void tap_stop(void) {
    if (current_port < 0) return;

    pio_sm_set_enabled(TAP_PIO, tap_sm, false);
    if (tap_dma >= 0) {
        dma_channel_abort(tap_dma);
    }
    pio_sm_unclaim(TAP_PIO, tap_sm);
    pio_remove_program(TAP_PIO, &recv_tap_program, tap_offset);

    current_port = -1;
    frame_len = 0;
    poll_pending = false;

#if TAP_TAKES_RX
    coax_restore();
#endif
}

int tap_port(void) {
    return current_port;
}

bool tap_holds_all_ports(void) {
    return TAP_TAKES_RX && current_port >= 0;
}

void tap_task(void) {
    if (current_port < 0) return;

    uint32_t write_index = dma_write_index();

    while (ring_read != write_index) {
        uint16_t word = ring[ring_read];
        ring_read = (ring_read + 1) & (RING_WORDS - 1);

        if (word == 0xffff) {
            frame_complete(0);
        } else if (frame_len < MAX_FRAME_LENGTH) {
            frame[frame_len++] = word;
        } else {
            // More words than a frame can hold: report what was decoded
            // and pick up again at the next end of frame marker.
            frame_complete(CAPTURE_FLAG_RX_ERROR);
        }
    }

    if (poll_pending && time_us_64() - poll_us > POLL_PAIR_TIMEOUT_US) {
        flush_poll();
    }

    // The transfer count is large enough to run for hours, but a tap that
    // is left running outlives it.
    if (!dma_channel_is_busy(tap_dma)) {
        start_dma();
    }
}
