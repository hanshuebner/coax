from machine import Pin, UART
import serial

dbg = UART(1, 115200, tx=Pin(20), rx=Pin(21))

def dprint(*a):
    try:
        dbg.write((" ".join(map(str, a)) + "\r\n"))
    except Exception:
        pass

