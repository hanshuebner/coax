#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/bootrom.h"
#include "tusb.h"

#include "coax.h"
#include "slip.h"
#include "command.h"
#include "capture.h"
#include "tap.h"
#include "leds.h"

// One SLIP decoder per command port, plus one for the capture port.
// A command port receives whole frames, the capture port only short
// control messages.
static slip_state_t slip_state[NUM_PORTS + 1];
static uint8_t command_buf[NUM_PORTS][SLIP_BUF_SIZE];
static uint8_t capture_buf[64];

// Commands are handled one at a time, so their responses share a buffer.
static uint8_t response[SLIP_BUF_SIZE];

static void cdc_write_all(int port, const uint8_t *data, int len) {
    int sent = 0;
    while (sent < len) {
        int avail = tud_cdc_n_write_available(port);
        if (avail > 0) {
            int chunk = len - sent;
            if (chunk > avail) chunk = avail;
            tud_cdc_n_write(port, data + sent, chunk);
            tud_cdc_n_write_flush(port);
            sent += chunk;
        }
        tud_task();
    }
}

// SLIP encode a message straight into the CDC, a chunk at a time.
static void cdc_send(int port, const uint8_t *data, int len) {
    uint8_t chunk[256];
    int pos = 0;

    chunk[pos++] = SLIP_END;
    for (int i = 0; i < len; i++) {
        if (pos + 2 > (int)sizeof(chunk)) {
            cdc_write_all(port, chunk, pos);
            pos = 0;
        }
        if (data[i] == SLIP_END) {
            chunk[pos++] = SLIP_ESC;
            chunk[pos++] = SLIP_ESC_END;
        } else if (data[i] == SLIP_ESC) {
            chunk[pos++] = SLIP_ESC;
            chunk[pos++] = SLIP_ESC_ESC;
        } else {
            chunk[pos++] = data[i];
        }
    }
    if (pos + 1 > (int)sizeof(chunk)) {
        cdc_write_all(port, chunk, pos);
        pos = 0;
    }
    chunk[pos++] = SLIP_END;
    cdc_write_all(port, chunk, pos);
}

// Opening any CDC port at 1200 baud restarts the chip in its USB
// bootloader, so new firmware can be loaded without reaching the board.
// The command protocol never sets a baud rate, so nothing else trips it.
#define BOOTLOADER_BAUD_RATE 1200

void tud_cdc_line_coding_cb(uint8_t itf, cdc_line_coding_t const *coding) {
    (void)itf;
    if (coding->bit_rate == BOOTLOADER_BAUD_RATE) {
        reset_usb_boot(0, 0);
    }
}

// Capture control commands arrive as SLIP frames on the capture port.
static void process_capture_port(void) {
    slip_state_t *s = &slip_state[CAPTURE_CDC_PORT];

    if (tud_cdc_n_connected(CAPTURE_CDC_PORT)) {
        int avail = tud_cdc_n_available(CAPTURE_CDC_PORT);
        if (avail > 0) {
            uint8_t tmp[64];
            int count = tud_cdc_n_read(CAPTURE_CDC_PORT, tmp, sizeof(tmp));
            int fed = 0;
            while (fed < count) {
                fed += slip_feed(s, tmp + fed, count - fed);
                if (slip_frame_ready(s)) {
                    capture_control(s->buf, s->len);
                    slip_frame_consume(s);
                }
            }
        }
    }

    capture_task();
}

// Commands taken off the host and responses written back to it. A host that
// waited for an answer it never received can be compared against these.
static uint32_t commands_handled;
static uint32_t responses_written;

uint32_t interface_commands_handled(void) { return commands_handled; }
uint32_t interface_responses_written(void) { return responses_written; }

static void process_port(int port) {
    if (!tud_cdc_n_connected(port)) return;

    int avail = tud_cdc_n_available(port);
    if (avail <= 0) return;

    uint8_t tmp[64];
    int count = tud_cdc_n_read(port, tmp, sizeof(tmp));
    if (count <= 0) return;

    // A read may hold the end of one frame and the start of the next, so
    // what the decoder leaves unread is fed again once the frame it
    // completed has been handled.
    int fed = 0;
    while (fed < count) {
        fed += slip_feed(&slip_state[port], tmp + fed, count - fed);

        if (!slip_frame_ready(&slip_state[port])) return;

        // Process the complete SLIP frame
        commands_handled++;

        int resp_len = command_process(port,
                                       slip_state[port].buf,
                                       slip_state[port].len,
                                       response,
                                       sizeof(response));

        slip_frame_consume(&slip_state[port]);

        if (resp_len > 0) {
            cdc_send(port, response, resp_len);
            responses_written++;
        }
    }
}

int main(void) {
    stdio_init_all();

    leds_init();
    leds_startup_show();

    tusb_init();

    coax_init();
    capture_init();

    for (int i = 0; i < NUM_PORTS; i++) {
        slip_init(&slip_state[i], command_buf[i], sizeof(command_buf[i]));
    }
    slip_init(&slip_state[CAPTURE_CDC_PORT], capture_buf, sizeof(capture_buf));

    while (true) {
        tud_task();

        for (int port = 0; port < NUM_PORTS; port++) {
            process_port(port);
        }

        process_capture_port();
        tap_task();

        leds_update();
    }

    return 0;
}
