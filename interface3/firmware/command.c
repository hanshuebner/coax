#include <string.h>
#include <stdio.h>
#include "pico/stdlib.h"
#include "command.h"
#include "coax.h"

uint32_t interface_commands_handled(void);
uint32_t interface_responses_written(void);
#include "capture.h"
#include "tap.h"
#include "leds.h"
#include "slip.h"

// Size of the message buffer reported to the host: a transmit/receive
// command carrying a frame of MAX_FRAME_LENGTH words, with its framing.
#define MAX_FRAME_SIZE   SLIP_BUF_SIZE

#define INFO_SUPPORTED_QUERIES  0x01
#define INFO_HARDWARE_TYPE      0x02
#define INFO_HARDWARE_REVISION  0x03
#define INFO_HARDWARE_SERIAL    0x04
#define INFO_FIRMWARE_VERSION   0x05
#define INFO_MESSAGE_BUFFER_SIZE 0x06
#define INFO_FEATURES           0x07
#define INFO_COUNTERS           0x08

#define FEATURE_PROTOCOL_3299   0x10

static int make_error(uint8_t *out, int out_size, uint8_t code, const char *desc) {
    int desc_len = desc ? strlen(desc) : 0;
    int payload_len = 2 + desc_len;
    int total = 2 + 1 + 1 + desc_len + 2;  // length(2) + response(1) + code(1) + desc + footer(2)
    if (total > out_size) return -1;

    out[0] = (payload_len >> 8) & 0xff;
    out[1] = payload_len & 0xff;
    out[2] = RESPONSE_ERROR;
    out[3] = code;
    if (desc_len > 0) memcpy(out + 4, desc, desc_len);
    out[4 + desc_len] = 0;
    out[5 + desc_len] = 0;
    return 4 + desc_len + 2;
}

static int cmd_reset(uint8_t *out, int out_size) {
    if (out_size < 7) return -1;
    // Match the MicroPython response: 00 03 01 32 70 00 00
    out[0] = 0x00; out[1] = 0x03;
    out[2] = 0x01; out[3] = 0x32; out[4] = 0x70;
    out[5] = 0x00; out[6] = 0x00;
    return 7;
}

static int cmd_info(const uint8_t *buf, int buf_len, uint8_t *out, int out_size) {
    if (buf_len < 1) return make_error(out, out_size, ERROR_INVALID_MESSAGE, "missing query");

    uint8_t query = buf[0];
    int pos = 0;

    if (query == INFO_SUPPORTED_QUERIES) {
        int payload_len = 7;
        out[pos++] = 0; out[pos++] = payload_len;
        out[pos++] = RESPONSE_OK;
        out[pos++] = INFO_SUPPORTED_QUERIES;
        out[pos++] = INFO_HARDWARE_TYPE;
        out[pos++] = INFO_FIRMWARE_VERSION;
        out[pos++] = INFO_MESSAGE_BUFFER_SIZE;
        out[pos++] = INFO_FEATURES;
        out[pos++] = INFO_COUNTERS;
        out[pos++] = 0; out[pos++] = 0;
        return pos;
    } else if (query == INFO_HARDWARE_TYPE) {
        int slen = strlen(HARDWARE_TYPE);
        int payload_len = 1 + slen;
        out[pos++] = (payload_len >> 8) & 0xff;
        out[pos++] = payload_len & 0xff;
        out[pos++] = RESPONSE_OK;
        memcpy(out + pos, HARDWARE_TYPE, slen);
        pos += slen;
        out[pos++] = 0; out[pos++] = 0;
        return pos;
    } else if (query == INFO_FIRMWARE_VERSION) {
        int slen = strlen(FIRMWARE_VERSION);
        int payload_len = 1 + slen;
        out[pos++] = (payload_len >> 8) & 0xff;
        out[pos++] = payload_len & 0xff;
        out[pos++] = RESPONSE_OK;
        memcpy(out + pos, FIRMWARE_VERSION, slen);
        pos += slen;
        out[pos++] = 0; out[pos++] = 0;
        return pos;
    } else if (query == INFO_MESSAGE_BUFFER_SIZE) {
        int payload_len = 5;
        out[pos++] = 0; out[pos++] = payload_len;
        out[pos++] = RESPONSE_OK;
        // Big-endian 32-bit buffer size
        out[pos++] = (MAX_FRAME_SIZE >> 24) & 0xff;
        out[pos++] = (MAX_FRAME_SIZE >> 16) & 0xff;
        out[pos++] = (MAX_FRAME_SIZE >> 8) & 0xff;
        out[pos++] = MAX_FRAME_SIZE & 0xff;
        out[pos++] = 0; out[pos++] = 0;
        return pos;
    } else if (query == INFO_COUNTERS) {
        // What the interface has counted since it started: transactions that
        // gave up waiting for the transmit DMA to drain.
        uint32_t counters[4] = {
            interface_commands_handled(),
            interface_responses_written(),
            coax_timeout_count(),
            coax_tx_drain_timeouts(),
        };
        int payload_len = 1 + 4 * 4;
        out[pos++] = 0; out[pos++] = payload_len;
        out[pos++] = RESPONSE_OK;
        for (int i = 0; i < 4; i++) {
            out[pos++] = (counters[i] >> 24) & 0xff;
            out[pos++] = (counters[i] >> 16) & 0xff;
            out[pos++] = (counters[i] >> 8) & 0xff;
            out[pos++] = counters[i] & 0xff;
        }
        out[pos++] = 0; out[pos++] = 0;
        return pos;
    } else if (query == INFO_FEATURES) {
        int payload_len = 1;
        out[pos++] = 0; out[pos++] = payload_len;
        out[pos++] = RESPONSE_OK;
        out[pos++] = 0; out[pos++] = 0;
        return pos;
    } else {
        return make_error(out, out_size, ERROR_INVALID_MESSAGE, "unknown query");
    }
}

static int cmd_transmit_receive(int port, const uint8_t *buf, int buf_len,
                                uint8_t *out, int out_size) {
    // Format: repeat_info(2) + coax_words(N) + response_length(2) + timeout(2)
    if (buf_len < 6) return make_error(out, out_size, ERROR_INVALID_MESSAGE, "too short");

    uint16_t timeout_ms = ((uint16_t)buf[buf_len - 2] << 8) | buf[buf_len - 1];

    // Coax words are between repeat_info and response_length/timeout
    const uint8_t *coax_words = buf + 2;
    int coax_words_len = buf_len - 6;

    if (coax_words_len < 2) return make_error(out, out_size, ERROR_INVALID_MESSAGE, "no words");

    if (!coax_available() || tap_port() == port) {
        return make_error(out, out_size, 105, "port is listening");
    }

    // Switch PIO to this port
    coax_switch_port(port);

    // Receive straight into the response, behind its length and response
    // code and leaving room for the footer: length(2) + RESPONSE_OK(1) +
    // rx_data + footer(2).
    if (out_size < 5) return -1;
    uint8_t *rx_data = out + 3;
    coax_timing_t timing;
    int rx_len = coax_transact(coax_words, coax_words_len, rx_data, out_size - 5,
                               timeout_ms, &timing);

    // A poll answered by 0x0000 leaves the terminal state unchanged.  A
    // terminal is polled continuously, so captures leave those out unless
    // they are asked for.
    bool is_empty_poll = (rx_len == 2 && rx_data[0] == 0 && rx_data[1] == 0);
    bool is_idle_poll = is_empty_poll && coax_words_len == 2;

    if (capture_port_active(port)) {
        if (is_idle_poll && !capture_wants_idle_polls(port)) {
            capture_count_idle_poll(port);
        } else if (rx_len == COAX_TIMEOUT) {
            if (capture_wants_timeouts(port)) {
                capture_frame(port, 0, coax_words, coax_words_len / 2, timing.tx_start_us);
                capture_frame(port, CAPTURE_FLAG_FROM_TERMINAL | CAPTURE_FLAG_TIMEOUT,
                              NULL, 0, timing.rx_end_us);
            }
        } else if (rx_len < 0) {
            capture_frame(port, 0, coax_words, coax_words_len / 2, timing.tx_start_us);
            capture_frame(port, CAPTURE_FLAG_FROM_TERMINAL | CAPTURE_FLAG_RX_ERROR,
                          NULL, 0, timing.rx_end_us);
        } else {
            capture_frame(port, 0, coax_words, coax_words_len / 2, timing.tx_start_us);
            capture_frame(port, CAPTURE_FLAG_FROM_TERMINAL, rx_data, rx_len / 2,
                          timing.rx_end_us);
        }
    }

    if (rx_len == COAX_TIMEOUT) {
        led_set_terminal_connected(port, false);
        return make_error(out, out_size, 102, "");  // ReceiveTimeout
    }
    if (rx_len < 0) {
        led_set_terminal_connected(port, false);
        return make_error(out, out_size, 105, "transact error");
    }

    led_set_terminal_connected(port, true);

    // Flash TX LED on successful transact, skip empty polls (0x0000)
    if (!is_empty_poll) {
        led_tx_activity(port);
    }

    // Complete the response around the received data
    int payload_len = 1 + rx_len;
    out[0] = (payload_len >> 8) & 0xff;
    out[1] = payload_len & 0xff;
    out[2] = RESPONSE_OK;
    int pos = 3 + rx_len;
    out[pos++] = 0; out[pos++] = 0;
    return pos;
}

int command_process(int port, const uint8_t *msg, int msg_len,
                    uint8_t *out_buf, int out_buf_size) {
    if (msg_len < 5) {  // 2 length + 1 command + 2 footer minimum
        return make_error(out_buf, out_buf_size, ERROR_INVALID_MESSAGE, "too short");
    }

    uint16_t length = ((uint16_t)msg[0] << 8) | msg[1];
    uint8_t command = msg[2];
    const uint8_t *payload = msg + 3;
    int payload_len = msg_len - 5;  // exclude 2-byte length, 1-byte cmd, 2-byte footer

    (void)length;

    switch (command) {
    case COMMAND_RESET:
        return cmd_reset(out_buf, out_buf_size);

    case COMMAND_INFO:
        return cmd_info(payload, payload_len, out_buf, out_buf_size);

    case COMMAND_TRANSMIT_RECEIVE:
        return cmd_transmit_receive(port, payload, payload_len, out_buf, out_buf_size);

    default:
        return make_error(out_buf, out_buf_size, ERROR_UNKNOWN_COMMAND, "unknown command");
    }
}
