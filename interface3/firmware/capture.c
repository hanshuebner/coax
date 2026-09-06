#include <string.h>

#include "pico/stdlib.h"
#include "tusb.h"

#include "capture.h"
#include "command.h"
#include "tap.h"
#include "forward.h"
#include "coax.h"
#include "slip.h"

#define RING_SIZE 16384
#define RING_MASK (RING_SIZE - 1)

#define CAPTURE_FORMAT_VERSION 1
#define META_FORMAT_VERSION    1

// SLIP encoded records waiting to go out over USB.  Producer and
// consumer both run in the main loop, so plain indices suffice.
static uint8_t ring[RING_SIZE];
static uint32_t ring_head;
static uint32_t ring_tail;

// Record being appended: the head to restore when it does not fit, and
// the port it belongs to so a discarded record is charged to that port.
static uint32_t record_start;
static bool record_overflow;
static int record_port;

static bool capturing;
static uint8_t port_mask;
static uint8_t options;
static uint16_t snap_words;

static uint32_t dropped;
static uint32_t dropped_reported;
static uint32_t dropped_port[NUM_PORTS];

static uint32_t frames_captured[NUM_PORTS];
static uint32_t idle_polls_suppressed[NUM_PORTS];

static bool port_open;

static uint32_t ring_used(void) {
    return (ring_head - ring_tail) & RING_MASK;
}

static void ring_reset(void) {
    ring_head = 0;
    ring_tail = 0;
    record_overflow = false;
}

// Append one byte without SLIP escaping.
static void put_raw(uint8_t b) {
    if (record_overflow) return;

    uint32_t next = (ring_head + 1) & RING_MASK;
    if (next == ring_tail) {
        record_overflow = true;
        return;
    }

    ring[ring_head] = b;
    ring_head = next;
}

static void put(uint8_t b) {
    if (b == SLIP_END) {
        put_raw(SLIP_ESC);
        put_raw(SLIP_ESC_END);
    } else if (b == SLIP_ESC) {
        put_raw(SLIP_ESC);
        put_raw(SLIP_ESC_ESC);
    } else {
        put_raw(b);
    }
}

static void put_u16le(uint16_t v) {
    put(v & 0xff);
    put((v >> 8) & 0xff);
}

static void put_u32le(uint32_t v) {
    for (int i = 0; i < 4; i++) {
        put((v >> (8 * i)) & 0xff);
    }
}

static void put_u64le(uint64_t v) {
    for (int i = 0; i < 8; i++) {
        put((uint8_t)((v >> (8 * i)) & 0xff));
    }
}

static void put_u16be(uint16_t v) {
    put((v >> 8) & 0xff);
    put(v & 0xff);
}

static void put_string(const char *s) {
    int len = strlen(s);
    if (len > 255) len = 255;
    put((uint8_t)len);
    for (int i = 0; i < len; i++) {
        put((uint8_t)s[i]);
    }
}

static void record_begin(uint8_t type, uint64_t ts_us, uint16_t incl_len, uint16_t orig_len) {
    record_start = ring_head;
    record_overflow = false;
    record_port = -1;

    put(type);
    put_u64le(ts_us);
    put_u16le(incl_len);
    put_u16le(orig_len);
}

// Close the record, or discard it whole when the ring ran out of room.
// Returns true when the record was committed.
static bool record_end(void) {
    put_raw(SLIP_END);

    if (record_overflow) {
        ring_head = record_start;
        record_overflow = false;
        dropped++;
        if (record_port >= 0) {
            dropped_port[record_port]++;
        }
        return false;
    }

    return true;
}

static void emit_meta(void) {
    const char *hw = HARDWARE_TYPE;
    const char *fw = FIRMWARE_VERSION;
    uint16_t body_len = 4 + 1 + strlen(hw) + 1 + strlen(fw);

    record_begin(CAPTURE_REC_META, time_us_64(), body_len, body_len);
    put(META_FORMAT_VERSION);
    put(NUM_PORTS);
    put_u16le(MAX_FRAME_LENGTH);
    put_string(hw);
    put_string(fw);
    record_end();
}

static void emit_drop(void) {
    uint16_t body_len = 4 + 4 * NUM_PORTS;

    record_begin(CAPTURE_REC_DROP, time_us_64(), body_len, body_len);
    put_u32le(dropped);
    for (int i = 0; i < NUM_PORTS; i++) {
        put_u32le(dropped_port[i]);
    }
    if (record_end()) {
        dropped_reported = dropped;
    }
}

static void emit_status(void) {
    uint16_t body_len = 1 + 1 + 1 + 2 + 4 + 3 * 4 * NUM_PORTS + 5;

    record_begin(CAPTURE_REC_STATUS, time_us_64(), body_len, body_len);
    put(capturing ? 1 : 0);
    put(port_mask);
    put(options);
    put_u16le(snap_words);
    put_u32le(dropped);
    for (int i = 0; i < NUM_PORTS; i++) {
        put_u32le(frames_captured[i]);
    }
    for (int i = 0; i < NUM_PORTS; i++) {
        put_u32le(idle_polls_suppressed[i]);
    }
    for (int i = 0; i < NUM_PORTS; i++) {
        put_u32le(dropped_port[i]);
    }
    put(tap_port() < 0 ? 0xff : (uint8_t)tap_port());
    put(forward_port_a() < 0 ? 0xff : (uint8_t)forward_port_a());
    put(forward_port_b() < 0 ? 0xff : (uint8_t)forward_port_b());
    put_u16le(forward_running() ? (uint16_t)forward_quiet_ns() : 0);
    record_end();
}

void capture_init(void) {
    ring_reset();
    capturing = false;
    port_mask = 0;
    options = CAPTURE_OPT_TIMEOUTS;
    snap_words = 0;
    dropped = 0;
    dropped_reported = 0;
    memset(dropped_port, 0, sizeof(dropped_port));
    memset(frames_captured, 0, sizeof(frames_captured));
    memset(idle_polls_suppressed, 0, sizeof(idle_polls_suppressed));
    port_open = false;
}

bool capture_port_active(int port) {
    return capturing && port >= 0 && port < NUM_PORTS && (port_mask & (1u << port));
}

bool capture_wants_idle_polls(int port) {
    return capture_port_active(port) && (options & CAPTURE_OPT_IDLE_POLLS);
}

bool capture_wants_timeouts(int port) {
    return capture_port_active(port) && (options & CAPTURE_OPT_TIMEOUTS);
}

void capture_count_idle_poll(int port) {
    if (port >= 0 && port < NUM_PORTS) {
        idle_polls_suppressed[port]++;
    }
}

void capture_frame(int port, uint8_t flags, const uint8_t *words,
                   int word_count, uint64_t ts_us) {
    if (!capture_port_active(port)) return;

    int included = word_count;
    if (snap_words > 0 && included > snap_words) {
        included = snap_words;
        flags |= CAPTURE_FLAG_TRUNCATED;
    }

    uint16_t incl_len = 6 + 2 * included;
    uint16_t orig_len = 6 + 2 * word_count;

    record_begin(CAPTURE_REC_FRAME, ts_us, incl_len, orig_len);
    record_port = port;
    put(CAPTURE_FORMAT_VERSION);
    put((uint8_t)port);
    put(flags);
    put(CAPTURE_ADDR_NONE);
    put_u16be((uint16_t)included);
    for (int i = 0; i < included; i++) {
        put_u16be((uint16_t)words[2 * i] | ((uint16_t)words[2 * i + 1] << 8));
    }
    record_end();

    frames_captured[port]++;
}

void capture_control(const uint8_t *msg, int len) {
    if (len < 1) return;

    switch (msg[0]) {
    case CAPTURE_CMD_START:
        if (len < 5) return;
        port_mask = msg[1];
        options = msg[2];
        snap_words = (uint16_t)msg[3] | ((uint16_t)msg[4] << 8);
        capturing = true;
        dropped = 0;
        dropped_reported = 0;
        memset(dropped_port, 0, sizeof(dropped_port));
        memset(frames_captured, 0, sizeof(frames_captured));
        memset(idle_polls_suppressed, 0, sizeof(idle_polls_suppressed));
        ring_reset();
        emit_meta();
        break;

    case CAPTURE_CMD_STOP:
        capturing = false;
        tap_stop();
        // Forwarding carries the link the interface sits in the middle of,
        // which outlives any one capture.  It stops when it is told to.
        break;

    case CAPTURE_CMD_STATUS:
        emit_status();
        break;

    case CAPTURE_CMD_FORWARD:
        if (len < 4) return;
        if (msg[3]) {
            unsigned quiet = len > 6 ? ((unsigned)msg[5] | ((unsigned)msg[6] << 8)) : 0;
            forward_start(msg[1], msg[2], len > 4 && (msg[4] & 1), quiet);
        } else {
            forward_stop();
        }
        emit_status();
        break;

    case CAPTURE_CMD_TAP:
        if (len < 3) return;
        if (msg[2]) {
            tap_start(msg[1]);
        } else {
            tap_stop();
        }
        emit_status();
        break;

    default:
        break;
    }
}

void capture_task(void) {
    bool connected = tud_cdc_n_connected(CAPTURE_CDC_PORT);

    if (connected != port_open) {
        port_open = connected;
        if (!connected) {
            capturing = false;
            tap_stop();
            ring_reset();
        }
    }

    if (!connected) return;

    if (capturing && dropped != dropped_reported) {
        emit_drop();
    }

    while (ring_used() > 0) {
        uint32_t avail = tud_cdc_n_write_available(CAPTURE_CDC_PORT);
        if (avail == 0) break;

        // Write up to the end of the ring, so the copy stays contiguous.
        uint32_t chunk = (ring_head > ring_tail) ? (ring_head - ring_tail)
                                                 : (RING_SIZE - ring_tail);
        if (chunk > avail) chunk = avail;

        uint32_t written = tud_cdc_n_write(CAPTURE_CDC_PORT, &ring[ring_tail], chunk);
        if (written == 0) break;

        ring_tail = (ring_tail + written) & RING_MASK;
    }

    tud_cdc_n_write_flush(CAPTURE_CDC_PORT);
}
