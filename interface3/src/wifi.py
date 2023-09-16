import network
import time
from leds import leds
from machine import Pin, Timer

led_net = leds['NET']

def blink(timer):
    global led_net
    led_net.toggle()


def connect(network_name, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(network_name, password)

    timer = Timer()
    timer.init(freq=8, mode=Timer.PERIODIC, callback=blink)

    old_status = -1
    connected = False
    while True:
        status = wlan.status()
        if status == old_status:
            continue
        elif status == -1:
            led_net.off()
            break
        elif status == 1:
            print("Connecting to WiFi network", network_name)
        elif status == 2:
            print("Acquiring IP address")
        elif status == 3:
            info = wlan.ifconfig()
            print("IP address:", info[0])
            connected = True
            led_net.on()
            break
        old_status = status
        time.sleep(0.5)

    timer.deinit()

    led_net.off()

    if not connected:
        print("Connection failed")
        leds['ERR'].on()
        return False

    return True
