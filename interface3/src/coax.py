import micropython
import rp2
import rp_devices as devs
import uctypes
import struct
from time import sleep, ticks_ms
from machine import Pin

PIN_XMIT = 2
PIN_DELAY = 3
PIN_RECV = 12
PIN_TEST = 13

dma = rp2.DMA()

TX_DMA_CHAN = dma.claim_unused_channel(True)
RX_DMA_CHAN = dma.claim_unused_channel(True)

DMA_CHAN_MASK = 1 << TX_DMA_CHAN | 1 << RX_DMA_CHAN

BIT_RATE = 2_358_700

MAX_FRAME_LENGTH = 80 * 25 + 16

# Maximum time to wait for a response from the terminal
TRANSACT_TIMEOUT_MS = 1_000


# xmit_serial: First word in FIFO defines frame length - 1 (i.e. 0 for
# 1 word). Every word to be transmitted is put in FIFO in manchester
# encording, including both the sync and the parity bit, for a total
# of 24 bits per word.  The data must be padded with a 8 zero bits to
# the right when placed in the FIFO.

# As in Andrew's doc https://github.com/lowobservable/coax/blob/master/protocol/protocol.md
# demo_words = ( 0b0101010101_000111_01_10101010_010110, 0b011001_01101111_000000000000000000 )
# demo_word = 0b01_10101010010110011001_01_00000000


@rp2.asm_pio(out_shiftdir=rp2.PIO.SHIFT_LEFT,
             out_init=rp2.PIO.OUT_LOW, set_init=rp2.PIO.OUT_LOW,
             fifo_join=rp2.PIO.JOIN_TX)
def xmit_serial():
    pull()
    mov(y, osr)
    pull()
    # generate 5 sync bits
    set(x, 4)
    label("sync")
    set(pins, 1)[5]
    set(pins, 0)[4]
    jmp(x_dec, "sync")
    # generate start pulse pattern (1/2 bit zero already into it)
    set(x, 23)  # initialize bit counter for first word
    nop()[10]
    set(pins, 1)[13]
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
    set(pins, 1)[5]
    set(pins, 0)[5]
    set(pins, 1)[23]
    set(pins, 0)


# xmit_serial_delay() generates the delayed TX signal required to generate the correct analog signal
# on the coax line

@rp2.asm_pio(set_init=rp2.PIO.OUT_LOW)
def xmit_serial_delay():
    wait(1, pin, 0)
    set(pins, 1)
    wait(0, pin, 0)
    set(pins, 0)


# recv_serial() receives and decodes frames, so there is no need for additional decoding of
# the words put into the FIFO.  Each frame is terminated by a 0xffffffff word in the FIFO.  The
# FIFO will usually be read in half-word (16bit) mode by DMA.

@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_LEFT,
             autopush=True, push_thresh=10,
             set_init=rp2.PIO.OUT_LOW,
             fifo_join=rp2.PIO.JOIN_RX)
def recv_serial():
    label("start_frame")
    wait(1, pin, 0)[7] # wait for quiescent bit
    jmp(pin, "start_frame")
    wait(1, pin, 0)
    wait(0, pin, 0)[2]  # wait for falling edge
    jmp(pin, "start_frame")[3]  # expect zero half bit
    jmp(pin, "start_frame")[3]  # expect zero half bit
    set(pins, 1)
    set(pins, 0)
    jmp(pin, "start_frame")[5]  # expect zero half bit
    jmp(pin, "one")[4]
    jmp("start_frame")
    label("one")
    jmp(pin, "two")[4]
    jmp("start_frame")
    label("two")
    jmp(pin, "three")
    jmp("start_frame")
    label("three")
    set(pins, 1)[5]
    set(x, 9)  # 10 bits to read
    # we are 1/4 bit into the sync/end bit
    label("word_loop")
    jmp(pin, "end_frame")[17]
    # we are 3/4 bits into the first data bit
    label("bit_loop")
    in_(pins, 1)  # read bit, wait for next
    set(pins, 0)
    set(pins, 1)[8]
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
    set(pins, 0)

recv = rp2.StateMachine(1, recv_serial, freq=12 * BIT_RATE,
                        in_base=Pin(PIN_RECV), jmp_pin=Pin(PIN_RECV),
                        set_base=Pin(PIN_TEST))
xmit = rp2.StateMachine(7, xmit_serial, freq=12 * BIT_RATE,
                        out_base=Pin(PIN_XMIT), set_base=Pin(PIN_XMIT))
xmit_delay = rp2.StateMachine(6, xmit_serial_delay, freq=12 * BIT_RATE,
                              in_base=Pin(PIN_XMIT), set_base=Pin(PIN_DELAY))


@micropython.viper
def manchester_encode_word(value: uint) -> uint:
    """
    Manchester encode the given (10 bit) integer value, adding a start and parity bit.  Shift
    eight bits to the right so that the resulting 32 bit value can be left shifted onto the
    coax interface.
    """
    parity = uint(0)
    encoded = uint(0b01)  # start bit
    mask = uint(0x200)  # mask for current bit
    for _ in range(10):
        encoded <<= 2
        if value & mask:
            encoded |= 0b01
            parity += 1
        else:
            encoded |= 0b10
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


def demo():
    """
    Non-DMA demo:  Send 2 words and receive them, FIFO provides buffering
    """
    recv.active(1)
    xmit_delay.active(0)
    xmit.active(0)
    xmit.put(1)  # frame length - 1
    xmit.put(manchester_encode_word(1))
    xmit.put(manchester_encode_word(23))

    xmit_delay.active(1)
    xmit.active(1)
    expected = 1
    while True:
        received = recv.get()
        if received & 0xff000000:
            break
        elif received == expected:
            expected = 23
        else:
            raise Exception("unexpected response")


def setup_tx_dma(buf):
    """
    Set up transmit DMA
    :param buf: bytearray with number of longs - 1 to send manchester encoded data to send
    """
    dma_chan = devs.DMA_CHANS[TX_DMA_CHAN]

    dma_chan.READ_ADDR_REG = uctypes.addressof(buf)
    dma_chan.WRITE_ADDR_REG = devs.PIO1_BASE + devs.PIO_TXF3_OFFSET
    dma_chan.TRANS_COUNT_REG = int(len(buf) / 4)

    dma_chan.CTRL_TRIG_REG = 0
    dma_chan.CTRL_TRIG.CHAIN_TO = TX_DMA_CHAN
    dma_chan.CTRL_TRIG.IRQ_QUIET = 1
    dma_chan.CTRL_TRIG.INCR_READ = 1
    dma_chan.CTRL_TRIG.INCR_WRITE = 0
    dma_chan.CTRL_TRIG.TREQ_SEL = devs.DREQ_PIO1_TX3
    dma_chan.CTRL_TRIG.DATA_SIZE = 2  # SIZE_WORD

    dma_chan.CTRL_TRIG.EN = 1

    xmit_delay.active(1)
    xmit.active(1)


def setup_rx_dma(buf):
    """
    Set up receive DMA into the given buffer
    :param buf: bytearray of words to receive
    """
    dma_chan = devs.DMA_CHANS[RX_DMA_CHAN]

    dma_chan.READ_ADDR_REG = devs.PIO0_BASE + devs.PIO_RXF1_OFFSET
    dma_chan.WRITE_ADDR_REG = uctypes.addressof(buf)
    dma_chan.TRANS_COUNT_REG = int(len(buf) / 2)

    dma_chan.CTRL_TRIG_REG = 0
    dma_chan.CTRL_TRIG.CHAIN_TO = RX_DMA_CHAN
    dma_chan.CTRL_TRIG.IRQ_QUIET = 1
    dma_chan.CTRL_TRIG.INCR_READ = 0
    dma_chan.CTRL_TRIG.INCR_WRITE = 1
    dma_chan.CTRL_TRIG.TREQ_SEL = devs.DREQ_PIO0_RX1
    dma_chan.CTRL_TRIG.DATA_SIZE = 1  # SIZE_HALFWORD

    dma_chan.CTRL_TRIG.EN = 1

    recv.active(1)


def transact(tx_buf):
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
    while receive_count == -1 and ticks_ms() - start < TRANSACT_TIMEOUT_MS:
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
    devs.DMA_CHANS[RX_DMA_CHAN].CTRL_TRIG.EN = 0
    devs.DMA_CHANS[TX_DMA_CHAN].CTRL_TRIG.EN = 0
    devs.DMA_DEVICE.CHAN_ABORT = DMA_CHAN_MASK
    while devs.DMA_DEVICE.CHAN_ABORT != 0:
        pass

    assert devs.DMA_CHANS[RX_DMA_CHAN].CTRL_TRIG.BUSY == 0
    assert devs.DMA_CHANS[RX_DMA_CHAN].CTRL_TRIG.EN == 0
    assert devs.DMA_CHANS[TX_DMA_CHAN].CTRL_TRIG.BUSY == 0
    assert devs.DMA_CHANS[TX_DMA_CHAN].CTRL_TRIG.EN == 0

    if receive_count == -1:
        print("tx", tx_buf[:32])
        print("rx", rx_buf[:32])
        raise RuntimeError('Timeout waiting for reply')

    return rx_buf[0:receive_count]
