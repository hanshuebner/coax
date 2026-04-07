#ifndef COMMAND_H
#define COMMAND_H

#include <stdint.h>

#define COMMAND_RESET             0x01
#define COMMAND_TRANSMIT_RECEIVE  0x06
#define COMMAND_INFO              0xF0
#define COMMAND_TEST              0xF1
#define COMMAND_DFU               0xF2

#define RESPONSE_OK    1
#define RESPONSE_ERROR 2

#define ERROR_INVALID_MESSAGE 1
#define ERROR_UNKNOWN_COMMAND 2
#define ERROR_MESSAGE_TIMEOUT 3

// Process a command received on a CDC port. Returns response in out_buf.
// Returns length of response, or -1 on error.
int command_process(int port, const uint8_t *msg, int msg_len,
                    uint8_t *out_buf, int out_buf_size);

#endif
