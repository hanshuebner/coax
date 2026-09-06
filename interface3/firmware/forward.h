#ifndef FORWARD_H
#define FORWARD_H

#include <stdbool.h>

// In-line forwarding: the interface sits in the middle of a link between a
// controller and a terminal, with one port to each end, and puts what
// arrives on either port straight back out on the other.  The line is
// copied bit by bit at the system clock rather than decoded and sent on,
// so a frame crosses in a few tens of nanoseconds.
//
// Both segments are terminated by the port they end at, which is what
// makes this transparent where bridging onto a live link is not.  The
// traffic of both ends appears on both wires, so a listener on either port
// records the whole conversation.
//
// Forwarding takes the instruction memory that transactions need, so it
// gives up the transaction programs while it runs.

// Start forwarding between two ports.  With invert set, the copy is
// inverted on its way out, for a line whose receiver and driver do not
// share a polarity.  quiet_ns is how long a line has to stay quiet before
// the transmitter following it is turned off: long enough to ride over the
// code violations inside a frame, short enough to leave the far end its
// turn to answer.  Zero takes the default.
bool forward_start(int port_a, int port_b, bool invert, unsigned quiet_ns);
void forward_stop(void);

bool forward_running(void);
unsigned forward_quiet_ns(void);
int forward_port_a(void);
int forward_port_b(void);

#endif
