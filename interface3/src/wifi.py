import network
import time
from machine import Pin, Timer

led = Pin("LED", Pin.OUT)

def blink(timer):
    global led
    led.toggle()


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
            break
        elif status == 1:
            print("Connecting to WiFi network", network_name)
        elif status == 2:
            print("Acquiring IP address")
        elif status == 3:
            info = wlan.ifconfig()
            print("IP address:", info[0])
            connected = True
            break
        old_status = status
        time.sleep(0.5)

    timer.deinit()
    led.off()

    if not connected:
        print("Connection failed")
        return False

    return True
