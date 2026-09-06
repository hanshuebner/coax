#ifndef TUSB_CONFIG_H
#define TUSB_CONFIG_H

#include "pico.h"

#define CFG_TUSB_RHPORT0_MODE   OPT_MODE_DEVICE

// Four command ports plus the capture port
#define CFG_TUD_CDC             5
#define CFG_TUD_CDC_RX_BUFSIZE  512
#define CFG_TUD_CDC_TX_BUFSIZE  512

#define CFG_TUD_MSC             0
#define CFG_TUD_HID             0
#define CFG_TUD_MIDI            0
#define CFG_TUD_VENDOR          0

#endif
