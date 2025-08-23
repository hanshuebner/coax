import micropython
import rp2
import rp_devices as devs
import uctypes
import struct
from time import sleep, ticks_ms
from machine import Pin

PIN_RX = 2
PIN_TX = 3
PIN_TX_ACTIVE = 4
PIN_TX_DELAY = 5
PIN_TEST = 6

PIN_LED_RX = 7
PIN_LED_TX = 8

tx_dma = rp2.DMA()
rx_dma = rp2.DMA()

# State machine number configuration.  The choice is pretty much
# arbitrary.  The correct DMA transmit selectors need to be chosen
# from the data sheet.

TX_SM_NUM = 7       # PIO1 SM3
TX_TREQ_SEL = 11    # DREQ_PIO1_TX3

TX_DELAY_SM_NUM = 6 # PIO1 SM2

RX_SM_NUM = 1       # PIO0 SM1
RX_TREQ_SEL = 5     # DREQ_PIO0_RX1

BIT_RATE = 2_358_700

MAX_FRAME_LENGTH = 80 * 25 + 16

# Maximum time to wait for a response from the terminal
TRANSACT_TIMEOUT_MS = 1_000

class Timeout(Exception):
    pass


# xmit_serial: First word in FIFO defines frame length - 1 (i.e. 0 for
# 1 word). Every word to be transmitted is put in FIFO in manchester
# encording, including both the sync and the parity bit, for a total
# of 24 bits per word.  The data must be padded with a 8 zero bits to
# the right when placed in the FIFO.

# As in Andrew's doc https://github.com/lowobservable/coax/blob/master/protocol/protocol.md
# demo_words = ( 0b0101010101_000111_01_10101010_010110, 0b011001_01101111_000000000000000000 )
# demo_word = 0b01_10101010010110011001_01_00000000


@rp2.asm_pio(out_shiftdir=rp2.PIO.SHIFT_LEFT,
             out_init=rp2.PIO.OUT_LOW,
             set_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW),
             fifo_join=rp2.PIO.JOIN_TX)
def xmit_serial():
    pull()
    mov(y, osr)
    pull()
    # generate 5 sync bits
    set(x, 4)
    label("sync")
    set(pins, 0b10)[5]
    set(pins, 0b11)[4]
    jmp(x_dec, "sync")
    # generate start pulse pattern (1/2 bit zero already into it)
    set(x, 23)[11]  # initialize bit counter for first word
    set(pins, 0b10)[13]
    # transmit word
    label("bit_loop_delay")
    nop()[3]
    label("bit_loop_nodelay")
    out(pins, 1)
    jmp(x_dec, "bit_loop_delay")
    jmp(not_y, "end_of_frame")
    pull()
    set(x, 23)  # set bit counter for this word
    jmp(y_dec, "bit_loop_nodelay")
    label("end_of_frame")
    nop()[2]
    set(pins, 0b10)[5]
    set(pins, 0b11)[5]
    set(pins, 0b10)[23]
    set(pins, 0b00)

# xmit_serial_delay() generates the delayed TX signal required to generate the correct analog signal
# on the coax line

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def xmit_serial_delay():
    wait(1, pin, 0)
    set(pins, 0)
    wait(0, pin, 0)
    set(pins, 1)


# recv_serial() receives and decodes frames, so there is no need for additional decoding of
# the words put into the FIFO.  Each frame is terminated by a 0xffffffff word in the FIFO.  The
# FIFO will usually be read in half-word (16bit) mode by DMA.

@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_LEFT,
             autopush=True, push_thresh=10,
             set_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW),
             fifo_join=rp2.PIO.JOIN_RX)
def recv_serial():
    # wait for end of transmission
    wait(1, pin, 2)
    wait(0, pin, 2)
    label("start0")
    wait(1, pin, 0) # wait for quiescent bit
    label("start1")
    wait(0, pin, 0)
    set(pins, 0b01)
    set(pins, 0b00)
    jmp(pin, "start1")[3]  # expect zero half bit
    jmp(pin, "start1")[5]  # expect zero half bit
    jmp(pin, "start1")[5]  # expect zero half bit
    jmp(pin, "vio10")[5]
    jmp("start0")
    label("vio10")
    jmp(pin, "vio11")[4]
    jmp("start0")
    label("vio11")
    jmp(pin, "vio12")
    jmp("start0")
    label("vio12")
    set(pins, 0b11)
    set(x, 9)  # 10 bits to read
    # wait for the beginning of the sync bit
    wait(0, pin, 0)
    # we are 1/4 bit into the sync/end bit
    label("word_loop")
    jmp(pin, "end_frame")
    # sync on the rising edge of the sync bit
    wait(1, pin, 0)[12]
    # we are 3/4 bits into the first data bit
    label("bit_loop")
    in_(pins, 1)  # read bit, wait for next
    set(pins, 0b10)
    set(pins, 0b11)[8]
    jmp(x_dec, "bit_loop")
    # looking at the parity bit now
    mov(x, pins)[3]
    set(x, 9)  # 10 bits to read
    # FIXME check parity
    jmp("word_loop")  # looking at 1/4 of sync/end again
    label("end_frame")
    set(x, 0)
    mov(isr, invert(x))
    push()
    label("wait_idle")
    jmp(pin, "wait_idle")
    set(pins, 0b00)

recv = rp2.StateMachine(RX_SM_NUM, recv_serial, freq=12 * BIT_RATE,
                        in_base=Pin(PIN_RX), jmp_pin=Pin(PIN_RX),
                        set_base=Pin(PIN_TEST))
xmit = rp2.StateMachine(TX_SM_NUM, xmit_serial, freq=12 * BIT_RATE,
                        out_base=Pin(PIN_TX), set_base=Pin(PIN_TX))
xmit_delay = rp2.StateMachine(TX_DELAY_SM_NUM, xmit_serial_delay, freq=12 * BIT_RATE,
                              in_base=Pin(PIN_TX), set_base=Pin(PIN_TX_DELAY))

@micropython.viper
def manchester_encode_word(value: uint) -> uint:
    """
    Manchester encode the given (10 bit) integer value, adding a start and parity bit.  Shift
    eight bits to the right so that the resulting 32 bit value can be left shifted onto the
    coax interface.
    """
    parity = uint(1)
    encoded = uint(0b10)  # start bit
    mask = uint(0x200)  # mask for current bit
    for _ in range(10):
        encoded <<= 2
        if value & mask:
            encoded |= 0b10
            parity += 1
        else:
            encoded |= 0b01
        mask >>= 1
    encoded <<= 2
    if parity & 1:
        encoded |= 0b10
    else:
        encoded |= 0b01
    encoded <<= 8
    return encoded


@micropython.native
def encode_tx_buf(tx_buf):
    """
    Set up transmission buffer - The first long word is the number of (encoded) words to send minus one, manchester
    encoded words follow.
    :param tx_buf: input data
    :return: buffer of longs ready for sending
    """
    tx_encoded = bytearray(len(tx_buf) * 2 + 4)
    tx_encoded[0:4] = struct.pack("<L", int(len(tx_buf) / 2) - 1)
    for i in range(0, len(tx_buf), 2):
        tx_encoded[i * 2 + 4:i * 2 + 8] = struct.pack("<L",
                                                      manchester_encode_word(struct.unpack("<H", tx_buf[i:i + 2])[0]))
    return tx_encoded


def demo(word=18):
    """
    Non-DMA demo:  Send 2 words and receive them, FIFO provides buffering
    """
    ret = []
    recv.active(1)
    xmit_delay.active(0)
    xmit.active(0)
    xmit.put(0)  # frame length - 1
    xmit.put(manchester_encode_word(word))

    xmit_delay.active(1)
    xmit.active(1)
    expected = 1
    while True:
        received = recv.get()
        ret.append(received)
        if received & 0xff000000:
            break
    return ret


def setup_tx_dma(buf):
    """
    Set up transmit DMA
    :param buf: bytearray with number of longs - 1 (manchester encoded) to send
    """

    tx_dma.config(
        read=uctypes.addressof(buf),
        write=xmit,
        count=int(len(buf) / 4),
        ctrl=tx_dma.pack_ctrl(
            size=2, # word
            inc_write=False,
            treq_sel=TX_TREQ_SEL),
        trigger=True)

    xmit_delay.restart()
    xmit_delay.active(1)
    xmit.restart()
    xmit.active(1)


def setup_rx_dma(buf):
    """
    Set up receive DMA into the given buffer
    :param buf: bytearray of words to receive
    """

    rx_dma.config(
        read=recv,
        write=uctypes.addressof(buf),
        count=int(len(buf) / 2),
        ctrl=rx_dma.pack_ctrl(
            size=1, # half word
            inc_read=False,
            treq_sel=RX_TREQ_SEL),
        trigger=True)

    recv.restart()
    recv.active(1)


def transact(tx_buf, timeout=TRANSACT_TIMEOUT_MS):
    """
    Perform a DMA send/receive operation
    :param tx_buf: bytearray with words to send
    """
    assert len(tx_buf) % 2 == 0

    # Set up receive buffer, one extra word for the end marker (0xffff)
    rx_buf = bytearray(MAX_FRAME_LENGTH * 2 + 2)

    tx_encoded = encode_tx_buf(tx_buf)

    # Initiate DMA transfers
    setup_rx_dma(rx_buf)
    setup_tx_dma(tx_encoded)

    # Wait for response
    start = ticks_ms()
    receive_count = -1
    while receive_count == -1 and ticks_ms() - start < timeout:
        # Try to find end of frame marker in DMA buffer
        for i in range(0, MAX_FRAME_LENGTH * 2, 2):
            if struct.unpack("<H", rx_buf[i:i + 2])[0] == 0xffff:
                receive_count = i
                break
        sleep(0.001)

    # Disable state machines
    recv.active(0)
    xmit.active(0)
    xmit_delay.active(0)

    # Abort DMA
    rx_dma.active(0)
    tx_dma.active(0)

    while rx_dma.active() or tx_dma.active():
        pass

    if receive_count == -1:
        raise Timeout()

    # print('rx: ', rx_buf[0:receive_count])

    return rx_buf[0:receive_count]

def receive():
    """
    Perform a DMA receive operation
    :param tx_buf: bytearray with words to send
    """

    # Set up receive buffer, one extra word for the end marker (0xffff)
    rx_buf = bytearray(MAX_FRAME_LENGTH * 2 + 2)

    # Initiate DMA transfers
    setup_rx_dma(rx_buf)

    # Manually toggle TX_ACTIVE to unblock receiver
    tx_active = Pin(PIN_TX_ACTIVE, Pin.OUT)
    tx_active.on()
    tx_active.off()

    # Wait for response
    start = ticks_ms()
    receive_count = -1
    while receive_count == -1:
        # Try to find end of frame marker in DMA buffer
        for i in range(0, MAX_FRAME_LENGTH * 2, 2):
            if struct.unpack("<H", rx_buf[i:i + 2])[0] == 0xffff:
                receive_count = i
                break
        sleep(0.001)

    # Disable state machines
    recv.active(0)

    # Abort DMA
    rx_dma.active(0)

    while rx_dma.active():
        pass

    print('rx ', receive_count, ': ', rx_buf[0:receive_count])

    return rx_buf[0:receive_count]
