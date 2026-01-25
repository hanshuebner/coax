from machine import Pin, UART
import serial

dbg = UART(1, 115200, tx=Pin(20), rx=Pin(21))

debug = False

def dprint(*a):
    if debug:
        try:
            dbg.write((" ".join(map(str, a)) + "\r\n"))
        except Exception:
            pass

