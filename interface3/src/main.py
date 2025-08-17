import wifi
import tcpserver
import time
import config
import leds

while not wifi.connect(config.wifi['ssid'], config.wifi['password']):
    time.sleep(1)

tcpserver.serve()
