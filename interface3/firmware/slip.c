#include "slip.h"

void slip_init(slip_state_t *s, uint8_t *buf, int size) {
    s->buf = buf;
    s->size = size;
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

        if (s->len < s->size) {
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
