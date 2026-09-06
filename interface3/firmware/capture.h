#ifndef CAPTURE_H
#define CAPTURE_H

#include <stdint.h>
#include <stdbool.h>

#include "coax.h"

// The capture CDC follows the four command CDCs.
#define CAPTURE_CDC_PORT NUM_PORTS

// Record types
#define CAPTURE_REC_FRAME   1
#define CAPTURE_REC_META    2
#define CAPTURE_REC_DROP    3
#define CAPTURE_REC_STATUS  4

// Link-layer frame flags
#define CAPTURE_FLAG_FROM_TERMINAL 0x01
#define CAPTURE_FLAG_TRUNCATED     0x02
#define CAPTURE_FLAG_TIMEOUT       0x04
#define CAPTURE_FLAG_RX_ERROR      0x08
#define CAPTURE_FLAG_INFERRED      0x10

// Control commands
#define CAPTURE_CMD_START   0x01
#define CAPTURE_CMD_STOP    0x02
#define CAPTURE_CMD_STATUS  0x03
#define CAPTURE_CMD_TAP     0x04
#define CAPTURE_CMD_FORWARD 0x05

// Capture options
#define CAPTURE_OPT_IDLE_POLLS 0x01
#define CAPTURE_OPT_TIMEOUTS   0x02

// 3299 multiplexer address used when the frame is not addressed
#define CAPTURE_ADDR_NONE 0xff

void capture_init(void);

// True while records are being recorded for the given port.  The
// transaction path uses this to skip building records nobody wants.
bool capture_port_active(int port);

// Record one coax frame.  Words are 10-bit values in 16-bit
// little-endian containers, as exchanged with the host and the PIO.
void capture_frame(int port, uint8_t flags, const uint8_t *words,
                   int word_count, uint64_t ts_us);

// Count a poll transaction that was suppressed by the idle poll filter.
void capture_count_idle_poll(int port);

// True when the idle poll filter is off for this port, i.e. polls
// answered by 0x0000 are to be recorded.
bool capture_wants_idle_polls(int port);

// True when timed out transactions are to be recorded.
bool capture_wants_timeouts(int port);

// Handle a control command received on the capture CDC.
void capture_control(const uint8_t *msg, int len);

// Move buffered records to USB and track the capture port connection.
void capture_task(void);

#endif
