#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "tusb.h"

#include "coax.h"
#include "slip.h"
#include "command.h"
#include "leds.h"

static slip_state_t slip_state[NUM_PORTS];

static void cdc_send(int port, const uint8_t *data, int len) {
    uint8_t slip_buf[SLIP_BUF_SIZE * 2];
    int encoded_len = slip_encode(data, len, slip_buf, sizeof(slip_buf));
    if (encoded_len < 0) return;

    int sent = 0;
    while (sent < encoded_len) {
        int avail = tud_cdc_n_write_available(port);
        if (avail > 0) {
            int chunk = encoded_len - sent;
            if (chunk > avail) chunk = avail;
            tud_cdc_n_write(port, slip_buf + sent, chunk);
            tud_cdc_n_write_flush(port);
            sent += chunk;
        }
        tud_task();
    }
}

static void process_port(int port) {
    if (!tud_cdc_n_connected(port)) return;

    int avail = tud_cdc_n_available(port);
    if (avail <= 0) return;

    uint8_t tmp[64];
    int count = tud_cdc_n_read(port, tmp, sizeof(tmp));
    if (count <= 0) return;

    slip_feed(&slip_state[port], tmp, count);

    if (!slip_frame_ready(&slip_state[port])) return;

    // Process the complete SLIP frame
    uint8_t response[SLIP_BUF_SIZE];
    int resp_len = command_process(port,
                                   slip_state[port].buf,
                                   slip_state[port].len,
                                   response,
                                   sizeof(response));

    slip_frame_consume(&slip_state[port]);

    if (resp_len > 0) {
        cdc_send(port, response, resp_len);
    }
}

int main(void) {
    stdio_init_all();

    leds_init();
    leds_startup_show();

    tusb_init();

    coax_init();

    for (int i = 0; i < NUM_PORTS; i++) {
        slip_init(&slip_state[i]);
    }

    while (true) {
        tud_task();

        for (int port = 0; port < NUM_PORTS; port++) {
            process_port(port);
        }

        leds_update();
    }

    return 0;
}
