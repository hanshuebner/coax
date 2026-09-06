#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"

#include "forward.h"
#include "coax.h"
#include "coax.pio.h"

// The repeaters and the transmit delay generators share the block that
// holds the transmit program, which forwarding gives up.
#define REPEAT_PIO pio1

#define DEFAULT_QUIET_NS 1000

static bool running;
static int port_a = -1;
static int port_b = -1;
static bool inverted;
static unsigned quiet_ns = DEFAULT_QUIET_NS;

static uint repeat_offset;
static uint delay_offset;
static uint repeat_sm[2];
static uint delay_sm[2];

// One direction of the pair: what arrives on the source port is put out on
// the destination port.
static void configure_repeat(uint sm, const coax_port_pins_t *src,
                             const coax_port_pins_t *dst) {
    pio_sm_config c = repeat_line_program_get_default_config(repeat_offset);

    sm_config_set_in_pins(&c, src->pin_rx);
    sm_config_set_jmp_pin(&c, src->pin_rx);
    sm_config_set_out_pins(&c, dst->pin_tx, 1);
    sm_config_set_set_pins(&c, dst->pin_tx_active, 1);
    sm_config_set_clkdiv(&c, 1.0f);  // sample at the system clock

    pio_gpio_init(REPEAT_PIO, dst->pin_tx);
    pio_gpio_init(REPEAT_PIO, dst->pin_tx_active);
    pio_sm_set_consecutive_pindirs(REPEAT_PIO, sm, dst->pin_tx, 1, true);
    pio_sm_set_consecutive_pindirs(REPEAT_PIO, sm, dst->pin_tx_active, 1, true);

    pio_sm_init(REPEAT_PIO, sm, repeat_offset, &c);

    // The quiet period, counted in passes through the three instruction
    // copy loop.
    uint32_t sample_hz = clock_get_hz(clk_sys) / 3;
    uint32_t quiet = (uint32_t)((uint64_t)sample_hz * quiet_ns / 1000000000u);
    if (quiet < 2) quiet = 2;
    pio_sm_put(REPEAT_PIO, sm, quiet);
}

// The driver wants a delayed copy of the transmitted signal alongside it.
static void configure_delay(uint sm, const coax_port_pins_t *dst) {
    pio_sm_config c = xmit_serial_delay_program_get_default_config(delay_offset);

    sm_config_set_in_pins(&c, dst->pin_tx);
    sm_config_set_set_pins(&c, dst->pin_tx_delay, 1);
    sm_config_set_clkdiv(&c, (float)clock_get_hz(clk_sys) / PIO_FREQ);

    pio_gpio_init(REPEAT_PIO, dst->pin_tx_delay);
    pio_sm_set_consecutive_pindirs(REPEAT_PIO, sm, dst->pin_tx_delay, 1, true);

    pio_sm_init(REPEAT_PIO, sm, delay_offset, &c);
}

static void release_pins(int port) {
    const coax_port_pins_t *p = &port_pins[port];
    const uint pins[] = { p->pin_tx, p->pin_tx_active, p->pin_tx_delay };

    gpio_set_outover(p->pin_tx, GPIO_OVERRIDE_NORMAL);

    for (int i = 0; i < 3; i++) {
        gpio_set_function(pins[i], GPIO_FUNC_SIO);
        gpio_set_dir(pins[i], GPIO_OUT);
        gpio_put(pins[i], 0);
    }
}

bool forward_start(int port_one, int port_two, bool invert, unsigned quiet) {
    if (port_one < 0 || port_one >= NUM_PORTS) return false;
    if (port_two < 0 || port_two >= NUM_PORTS) return false;
    if (port_one == port_two) return false;

    forward_stop();

    quiet_ns = quiet > 0 ? quiet : DEFAULT_QUIET_NS;

    // Transactions and forwarding cannot both hold the instruction memory.
    coax_release();

    if (!pio_can_add_program(REPEAT_PIO, &repeat_line_program)) {
        coax_restore();
        return false;
    }

    repeat_offset = pio_add_program(REPEAT_PIO, &repeat_line_program);
    delay_offset = pio_add_program(REPEAT_PIO, &xmit_serial_delay_program);

    for (int i = 0; i < 2; i++) {
        repeat_sm[i] = pio_claim_unused_sm(REPEAT_PIO, true);
        delay_sm[i] = pio_claim_unused_sm(REPEAT_PIO, true);
    }

    const coax_port_pins_t *pins[2] = { &port_pins[port_one], &port_pins[port_two] };

    for (int i = 0; i < 2; i++) {
        gpio_init(pins[i]->pin_rx);
        gpio_set_dir(pins[i]->pin_rx, GPIO_IN);
    }

    // A line whose receiver and driver disagree about polarity is put
    // right on its way out of the pin.
    if (invert) {
        gpio_set_outover(pins[0]->pin_tx, GPIO_OVERRIDE_INVERT);
        gpio_set_outover(pins[1]->pin_tx, GPIO_OVERRIDE_INVERT);
    }

    configure_repeat(repeat_sm[0], pins[0], pins[1]);
    configure_repeat(repeat_sm[1], pins[1], pins[0]);
    configure_delay(delay_sm[0], pins[0]);
    configure_delay(delay_sm[1], pins[1]);

    for (int i = 0; i < 2; i++) {
        pio_sm_set_enabled(REPEAT_PIO, delay_sm[i], true);
        pio_sm_set_enabled(REPEAT_PIO, repeat_sm[i], true);
    }

    port_a = port_one;
    port_b = port_two;
    inverted = invert;
    running = true;

    return true;
}

void forward_stop(void) {
    if (!running) return;

    for (int i = 0; i < 2; i++) {
        pio_sm_set_enabled(REPEAT_PIO, repeat_sm[i], false);
        pio_sm_set_enabled(REPEAT_PIO, delay_sm[i], false);
        pio_sm_unclaim(REPEAT_PIO, repeat_sm[i]);
        pio_sm_unclaim(REPEAT_PIO, delay_sm[i]);
    }

    pio_remove_program(REPEAT_PIO, &repeat_line_program, repeat_offset);
    pio_remove_program(REPEAT_PIO, &xmit_serial_delay_program, delay_offset);

    release_pins(port_a);
    release_pins(port_b);

    running = false;
    port_a = -1;
    port_b = -1;
    inverted = false;

    coax_restore();
}

bool forward_running(void) {
    return running;
}

unsigned forward_quiet_ns(void) {
    return quiet_ns;
}

int forward_port_a(void) {
    return port_a;
}

int forward_port_b(void) {
    return port_b;
}
