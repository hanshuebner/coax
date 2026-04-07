#include <string.h>
#include <stdio.h>
#include "pico/stdlib.h"
#include "command.h"
#include "coax.h"
#include "leds.h"

#define HARDWARE_TYPE    "interface3"
#define FIRMWARE_VERSION "v1.0"
#define MAX_FRAME_SIZE   4300

#define INFO_SUPPORTED_QUERIES  0x01
#define INFO_HARDWARE_TYPE      0x02
#define INFO_HARDWARE_REVISION  0x03
#define INFO_HARDWARE_SERIAL    0x04
#define INFO_FIRMWARE_VERSION   0x05
#define INFO_MESSAGE_BUFFER_SIZE 0x06
#define INFO_FEATURES           0x07

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
        int payload_len = 6;
        out[pos++] = 0; out[pos++] = payload_len;
        out[pos++] = RESPONSE_OK;
        out[pos++] = INFO_SUPPORTED_QUERIES;
        out[pos++] = INFO_HARDWARE_TYPE;
        out[pos++] = INFO_FIRMWARE_VERSION;
        out[pos++] = INFO_MESSAGE_BUFFER_SIZE;
        out[pos++] = INFO_FEATURES;
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

    // Switch PIO to this port
    coax_switch_port(port);

    // Flash activity LED
    led_set(port_pins[port].pin_led, true);

    // Perform transaction
    uint8_t rx_data[MAX_FRAME_LENGTH * 2];
    int rx_len = coax_transact(coax_words, coax_words_len, rx_data, sizeof(rx_data), timeout_ms);

    led_set(port_pins[port].pin_led, false);

    if (rx_len == COAX_TIMEOUT) {
        return make_error(out, out_size, 102, "");  // ReceiveTimeout
    }
    if (rx_len < 0) {
        return make_error(out, out_size, 105, "transact error");
    }

    // Build response: length(2) + RESPONSE_OK(1) + rx_data + footer(2)
    int payload_len = 1 + rx_len;
    int total = 2 + 1 + rx_len + 2;
    if (total > out_size) return -1;

    int pos = 0;
    out[pos++] = (payload_len >> 8) & 0xff;
    out[pos++] = payload_len & 0xff;
    out[pos++] = RESPONSE_OK;
    memcpy(out + pos, rx_data, rx_len);
    pos += rx_len;
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
