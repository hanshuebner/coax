#ifndef TAP_H
#define TAP_H

#include <stdbool.h>

// Listening capture: decode the traffic on a port the interface does not
// drive, so a link between a controller and a terminal can be recorded.
//
// The tapped port is given over to listening: transactions on it are
// refused while the tap runs.  On a chip whose PIO instruction memory is
// fully taken by the transmit and receive programs, the tap takes the
// place of the receive program and transactions are refused on every
// port; tap_holds_all_ports() reports which of the two applies.

bool tap_start(int port);
void tap_stop(void);

// The port being listened to, or -1 when no tap runs.
int tap_port(void);

// True when the tap has taken the receive program's instruction memory,
// leaving no port able to perform transactions.
bool tap_holds_all_ports(void);

// Move decoded frames from the receive ring into the capture stream.
void tap_task(void);

#endif
