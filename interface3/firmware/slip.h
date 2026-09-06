#ifndef SLIP_H
#define SLIP_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#include "coax.h"

#define SLIP_END     0xC0
#define SLIP_ESC     0xDB
#define SLIP_ESC_END 0xDC
#define SLIP_ESC_ESC 0xDD

// Room for a transmit/receive command or its response carrying a frame
// of MAX_FRAME_LENGTH words: length(2) + command(1) + repeat info(2) +
// words + response length(2) + timeout(2) + footer(2).
#define SLIP_BUF_SIZE (2 * MAX_FRAME_LENGTH + 16)

// Decoder state.  The frame buffer is supplied by the owner, so a port
// that only ever sees short control messages need not carry a full one.
typedef struct {
    uint8_t *buf;
    int size;
    int len;
    bool escaped;
    bool frame_ready;
} slip_state_t;

void slip_init(slip_state_t *s, uint8_t *buf, int size);
void slip_feed(slip_state_t *s, const uint8_t *data, int count);
bool slip_frame_ready(const slip_state_t *s);
int slip_frame_len(const slip_state_t *s);
void slip_frame_consume(slip_state_t *s);

#endif
