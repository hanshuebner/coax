import network
import time
from machine import Pin, Timer

PIN_LED_WIFI = 9

# We operate both the Pico and the externally connected LED.
led1 = Pin("LED", Pin.OUT)
led2 = Pin(PIN_LED_WIFI, Pin.OUT)

def blink(timer):
    global led1, led2
    led1.toggle()
    led2.toggle()


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
            led1.off()
            led2.off()
            break
        elif status == 1:
            print("Connecting to WiFi network", network_name)
        elif status == 2:
            print("Acquiring IP address")
        elif status == 3:
            info = wlan.ifconfig()
            print("IP address:", info[0])
            connected = True
            led1.on()
            led2.on()
            break
        old_status = status
        time.sleep(0.5)

    timer.deinit()

    if not connected:
        print("Connection failed")
        return False

    return True
