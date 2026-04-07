#ifndef SLIP_H
#define SLIP_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define SLIP_END     0xC0
#define SLIP_ESC     0xDB
#define SLIP_ESC_END 0xDC
#define SLIP_ESC_ESC 0xDD

#define SLIP_BUF_SIZE 4300

typedef struct {
    uint8_t buf[SLIP_BUF_SIZE];
    int len;
    bool escaped;
    bool frame_ready;
} slip_state_t;

void slip_init(slip_state_t *s);
void slip_feed(slip_state_t *s, const uint8_t *data, int count);
bool slip_frame_ready(const slip_state_t *s);
int slip_frame_len(const slip_state_t *s);
void slip_frame_consume(slip_state_t *s);

int slip_encode(const uint8_t *data, int len, uint8_t *out, int out_size);

#endif
