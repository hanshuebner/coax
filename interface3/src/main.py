import wifi
import webserver
import time
import config
import leds

while not wifi.connect(config.wifi['ssid'], config.wifi['password']):
    time.sleep(1)

webserver.serve()
