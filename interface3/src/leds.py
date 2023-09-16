from machine import Pin
from time import sleep

led_defs = ((8, 'TX1'),
            (7, 'RX1'),
            (13, 'TX2'),
            (12, 'RX2'),
            (1, 'TX3'),
            (0, 'RX3'),
            (28, 'TX4'),
            (6, 'RX4'),
            (22, 'NET'),
            (26, 'STS'),
            (27, 'ERR'),
            ('LED', 'PICO'))

leds = {}

def init():
    for (pin, name) in led_defs:
        leds[name] = Pin(pin, Pin.OUT)
    # initialization light show
    for (_, name) in led_defs:
        leds[name].on()
        sleep(0.03)
    for (_, name) in led_defs:
        leds[name].off()
        sleep(0.03)

init()
