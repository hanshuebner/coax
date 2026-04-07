#include "tusb.h"

// USB VID/PID — using test PIDs, replace for production
#define USB_VID 0x1209
#define USB_PID 0x0001

#define USB_BCD 0x0200

// String descriptor indices
enum {
    STRID_LANGID = 0,
    STRID_MANUFACTURER,
    STRID_PRODUCT,
    STRID_SERIAL,
    STRID_CDC0,
    STRID_CDC1,
    STRID_CDC2,
    STRID_CDC3,
};

// Endpoint numbers — each CDC needs 2 endpoints (notification IN + data IN/OUT)
// EP0 is control. We assign:
//   CDC0: notif=0x81, out=0x02, in=0x82
//   CDC1: notif=0x83, out=0x04, in=0x84
//   CDC2: notif=0x85, out=0x06, in=0x86
//   CDC3: notif=0x87, out=0x08, in=0x88

#define EPNUM_CDC0_NOTIF 0x81
#define EPNUM_CDC0_OUT   0x02
#define EPNUM_CDC0_IN    0x82

#define EPNUM_CDC1_NOTIF 0x83
#define EPNUM_CDC1_OUT   0x04
#define EPNUM_CDC1_IN    0x84

#define EPNUM_CDC2_NOTIF 0x85
#define EPNUM_CDC2_OUT   0x06
#define EPNUM_CDC2_IN    0x86

#define EPNUM_CDC3_NOTIF 0x87
#define EPNUM_CDC3_OUT   0x08
#define EPNUM_CDC3_IN    0x88

// Device descriptor
tusb_desc_device_t const desc_device = {
    .bLength            = sizeof(tusb_desc_device_t),
    .bDescriptorType    = TUSB_DESC_DEVICE,
    .bcdUSB             = USB_BCD,
    .bDeviceClass       = TUSB_CLASS_MISC,
    .bDeviceSubClass    = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol    = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0    = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor           = USB_VID,
    .idProduct          = USB_PID,
    .bcdDevice          = 0x0100,
    .iManufacturer      = STRID_MANUFACTURER,
    .iProduct           = STRID_PRODUCT,
    .iSerialNumber      = STRID_SERIAL,
    .bNumConfigurations = 0x01,
};

uint8_t const *tud_descriptor_device_cb(void) {
    return (uint8_t const *)&desc_device;
}

// Configuration descriptor
#define CONFIG_TOTAL_LEN (TUD_CONFIG_DESC_LEN + 4 * TUD_CDC_DESC_LEN)

uint8_t const desc_configuration[] = {
    TUD_CONFIG_DESCRIPTOR(1, 8, 0, CONFIG_TOTAL_LEN, 0x00, 100),

    TUD_CDC_DESCRIPTOR(0, STRID_CDC0, EPNUM_CDC0_NOTIF, 8, EPNUM_CDC0_OUT, EPNUM_CDC0_IN, 64),
    TUD_CDC_DESCRIPTOR(2, STRID_CDC1, EPNUM_CDC1_NOTIF, 8, EPNUM_CDC1_OUT, EPNUM_CDC1_IN, 64),
    TUD_CDC_DESCRIPTOR(4, STRID_CDC2, EPNUM_CDC2_NOTIF, 8, EPNUM_CDC2_OUT, EPNUM_CDC2_IN, 64),
    TUD_CDC_DESCRIPTOR(6, STRID_CDC3, EPNUM_CDC3_NOTIF, 8, EPNUM_CDC3_OUT, EPNUM_CDC3_IN, 64),
};

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
    (void)index;
    return desc_configuration;
}

// String descriptors
static char const *string_desc_arr[] = {
    [STRID_LANGID]       = (const char[]){0x09, 0x04},  // English
    [STRID_MANUFACTURER] = "coax-tcp",
    [STRID_PRODUCT]      = "Coax Interface",
    [STRID_SERIAL]       = "000000",
    [STRID_CDC0]         = "Coax Port 1",
    [STRID_CDC1]         = "Coax Port 2",
    [STRID_CDC2]         = "Coax Port 3",
    [STRID_CDC3]         = "Coax Port 4",
};

static uint16_t desc_str[32 + 1];

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    (void)langid;
    uint8_t chr_count;

    if (index == 0) {
        memcpy(&desc_str[1], string_desc_arr[0], 2);
        chr_count = 1;
    } else {
        if (index >= sizeof(string_desc_arr) / sizeof(string_desc_arr[0]))
            return NULL;

        const char *str = string_desc_arr[index];
        chr_count = strlen(str);
        if (chr_count > 31) chr_count = 31;

        for (uint8_t i = 0; i < chr_count; i++) {
            desc_str[1 + i] = str[i];
        }
    }

    desc_str[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * chr_count + 2));
    return desc_str;
}
