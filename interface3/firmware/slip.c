#include "slip.h"
#include <string.h>

void slip_init(slip_state_t *s) {
    s->len = 0;
    s->escaped = false;
    s->frame_ready = false;
}

void slip_feed(slip_state_t *s, const uint8_t *data, int count) {
    for (int i = 0; i < count; i++) {
        if (s->frame_ready) return;  // don't overwrite a pending frame

        uint8_t b = data[i];

        if (b == SLIP_END) {
            if (s->len > 0) {
                s->frame_ready = true;
            }
            continue;
        }

        if (s->escaped) {
            if (b == SLIP_ESC_END) {
                b = SLIP_END;
            } else if (b == SLIP_ESC_ESC) {
                b = SLIP_ESC;
            }
            s->escaped = false;
        } else if (b == SLIP_ESC) {
            s->escaped = true;
            continue;
        }

        if (s->len < SLIP_BUF_SIZE) {
            s->buf[s->len++] = b;
        }
    }
}

bool slip_frame_ready(const slip_state_t *s) {
    return s->frame_ready;
}

int slip_frame_len(const slip_state_t *s) {
    return s->len;
}

void slip_frame_consume(slip_state_t *s) {
    s->len = 0;
    s->escaped = false;
    s->frame_ready = false;
}

int slip_encode(const uint8_t *data, int len, uint8_t *out, int out_size) {
    int pos = 0;

    if (pos >= out_size) return -1;
    out[pos++] = SLIP_END;

    for (int i = 0; i < len; i++) {
        if (data[i] == SLIP_END) {
            if (pos + 2 > out_size) return -1;
            out[pos++] = SLIP_ESC;
            out[pos++] = SLIP_ESC_END;
        } else if (data[i] == SLIP_ESC) {
            if (pos + 2 > out_size) return -1;
            out[pos++] = SLIP_ESC;
            out[pos++] = SLIP_ESC_ESC;
        } else {
            if (pos + 1 > out_size) return -1;
            out[pos++] = data[i];
        }
    }

    if (pos >= out_size) return -1;
    out[pos++] = SLIP_END;

    return pos;
}
