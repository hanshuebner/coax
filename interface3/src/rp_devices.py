# RP2040 uctype definitions for MicroPython
# See https://iosoft.blog/pico-adc-dma for description
#
# Copyright (c) 2021 Jeremy P Bentham
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from uctypes import BF_POS, BF_LEN, UINT32, BFUINT32, struct

GPIO_CHAN_WIDTH = 0x08
GPIO_PIN_COUNT  = 30
PAD_PIN_WIDTH   = 0x04
DMA_CHAN_WIDTH  = 0x40
DMA_CHAN_COUNT  = 12

# memory and device base addresses
ROM_BASE                 = 0x00000000
XIP_BASE                 = 0x10000000
XIP_MAIN_BASE            = 0x10000000
XIP_NOALLOC_BASE         = 0x11000000
XIP_NOCACHE_BASE         = 0x12000000
XIP_NOCACHE_NOALLOC_BASE = 0x13000000
XIP_CTRL_BASE            = 0x14000000
XIP_SRAM_BASE            = 0x15000000
XIP_SRAM_END             = 0x15004000
XIP_SSI_BASE             = 0x18000000
SRAM_BASE                = 0x20000000
SRAM_STRIPED_BASE        = 0x20000000
SRAM_STRIPED_END         = 0x20040000
SRAM4_BASE               = 0x20040000
SRAM5_BASE               = 0x20041000
SRAM_END                 = 0x20042000
SRAM0_BASE               = 0x21000000
SRAM1_BASE               = 0x21010000
SRAM2_BASE               = 0x21020000
SRAM3_BASE               = 0x21030000
SYSINFO_BASE             = 0x40000000
SYSCFG_BASE              = 0x40004000
CLOCKS_BASE              = 0x40008000
RESETS_BASE              = 0x4000c000
PSM_BASE                 = 0x40010000
IO_BANK0_BASE            = 0x40014000
IO_QSPI_BASE             = 0x40018000
PADS_BANK0_BASE          = 0x4001c000
PADS_QSPI_BASE           = 0x40020000
XOSC_BASE                = 0x40024000
PLL_SYS_BASE             = 0x40028000
PLL_USB_BASE             = 0x4002c000
BUSCTRL_BASE             = 0x40030000
UART0_BASE               = 0x40034000
UART1_BASE               = 0x40038000
SPI0_BASE                = 0x4003c000
SPI1_BASE                = 0x40040000
I2C0_BASE                = 0x40044000
I2C1_BASE                = 0x40048000
ADC_BASE                 = 0x4004c000
PWM_BASE                 = 0x40050000
TIMER_BASE               = 0x40054000
WATCHDOG_BASE            = 0x40058000
RTC_BASE                 = 0x4005c000
ROSC_BASE                = 0x40060000
VREG_AND_CHIP_RESET_BASE = 0x40064000
TBMAN_BASE               = 0x4006c000
DMA_BASE                 = 0x50000000
USBCTRL_DPRAM_BASE       = 0x50100000
USBCTRL_BASE             = 0x50100000
USBCTRL_REGS_BASE        = 0x50110000
PIO0_BASE                = 0x50200000
PIO1_BASE                = 0x50300000
XIP_AUX_BASE             = 0x50400000
SIO_BASE                 = 0xd0000000
PPB_BASE                 = 0xe0000000

# PIO:
PIO_CTRL_OFFSET              = 0x00000000
PIO_FSTAT_OFFSET             = 0x00000004
PIO_FDEBUG_OFFSET            = 0x00000008
PIO_FLEVEL_OFFSET            = 0x0000000c
PIO_TXF0_OFFSET              = 0x00000010
PIO_TXF1_OFFSET              = 0x00000014
PIO_TXF2_OFFSET              = 0x00000018
PIO_TXF3_OFFSET              = 0x0000001c
PIO_RXF0_OFFSET              = 0x00000020
PIO_RXF1_OFFSET              = 0x00000024
PIO_RXF2_OFFSET              = 0x00000028
PIO_RXF3_OFFSET              = 0x0000002c
PIO_IRQ_OFFSET               = 0x00000030
PIO_IRQ_FORCE_OFFSET         = 0x00000034
PIO_INPUT_SYNC_BYPASS_OFFSET = 0x00000038
PIO_DBG_PADOUT_OFFSET        = 0x0000003c
PIO_DBG_PADOE_OFFSET         = 0x00000040
PIO_DBG_CFGINFO_OFFSET       = 0x00000044
PIO_INSTR_MEM0_OFFSET        = 0x00000048
PIO_INSTR_MEM1_OFFSET        = 0x0000004c
PIO_INSTR_MEM2_OFFSET        = 0x00000050
PIO_INSTR_MEM3_OFFSET        = 0x00000054
PIO_INSTR_MEM4_OFFSET        = 0x00000058
PIO_INSTR_MEM5_OFFSET        = 0x0000005c
PIO_INSTR_MEM6_OFFSET        = 0x00000060
PIO_INSTR_MEM7_OFFSET        = 0x00000064
PIO_INSTR_MEM8_OFFSET        = 0x00000068
PIO_INSTR_MEM9_OFFSET        = 0x0000006c
PIO_INSTR_MEM10_OFFSET       = 0x00000070
PIO_INSTR_MEM11_OFFSET       = 0x00000074
PIO_INSTR_MEM12_OFFSET       = 0x00000078
PIO_INSTR_MEM13_OFFSET       = 0x0000007c
PIO_INSTR_MEM14_OFFSET       = 0x00000080
PIO_INSTR_MEM15_OFFSET       = 0x00000084
PIO_INSTR_MEM16_OFFSET       = 0x00000088
PIO_INSTR_MEM17_OFFSET       = 0x0000008c
PIO_INSTR_MEM18_OFFSET       = 0x00000090
PIO_INSTR_MEM19_OFFSET       = 0x00000094
PIO_INSTR_MEM20_OFFSET       = 0x00000098
PIO_INSTR_MEM21_OFFSET       = 0x0000009c
PIO_INSTR_MEM22_OFFSET       = 0x000000a0
PIO_INSTR_MEM23_OFFSET       = 0x000000a4
PIO_INSTR_MEM24_OFFSET       = 0x000000a8
PIO_INSTR_MEM25_OFFSET       = 0x000000ac
PIO_INSTR_MEM26_OFFSET       = 0x000000b0
PIO_INSTR_MEM27_OFFSET       = 0x000000b4
PIO_INSTR_MEM28_OFFSET       = 0x000000b8
PIO_INSTR_MEM29_OFFSET       = 0x000000bc
PIO_INSTR_MEM30_OFFSET       = 0x000000c0
PIO_INSTR_MEM31_OFFSET       = 0x000000c4
PIO_SM0_CLKDIV_OFFSET        = 0x000000c8
PIO_SM0_EXECCTRL_OFFSET      = 0x000000cc
PIO_SM0_SHIFTCTRL_OFFSET     = 0x000000d0
PIO_SM0_ADDR_OFFSET          = 0x000000d4
PIO_SM0_INSTR_OFFSET         = 0x000000d8
PIO_SM0_PINCTRL_OFFSET       = 0x000000dc
PIO_SM1_CLKDIV_OFFSET        = 0x000000e0
PIO_SM1_EXECCTRL_OFFSET      = 0x000000e4
PIO_SM1_SHIFTCTRL_OFFSET     = 0x000000e8
PIO_SM1_ADDR_OFFSET          = 0x000000ec
PIO_SM1_INSTR_OFFSET         = 0x000000f0
PIO_SM1_PINCTRL_OFFSET       = 0x000000f4
PIO_SM2_CLKDIV_OFFSET        = 0x000000f8
PIO_SM2_EXECCTRL_OFFSET      = 0x000000fc
PIO_SM2_SHIFTCTRL_OFFSET     = 0x00000100
PIO_SM2_ADDR_OFFSET          = 0x00000104
PIO_SM2_INSTR_OFFSET         = 0x00000108
PIO_SM2_PINCTRL_OFFSET       = 0x0000010c
PIO_SM3_CLKDIV_OFFSET        = 0x00000110
PIO_SM3_EXECCTRL_OFFSET      = 0x00000114
PIO_SM3_SHIFTCTRL_OFFSET     = 0x00000118
PIO_SM3_ADDR_OFFSET          = 0x0000011c
PIO_SM3_INSTR_OFFSET         = 0x00000120
PIO_SM3_PINCTRL_OFFSET       = 0x00000124
PIO_INTR_OFFSET              = 0x00000128
PIO_IRQ0_INTE_OFFSET         = 0x0000012c
PIO_IRQ0_INTF_OFFSET         = 0x00000130
PIO_IRQ0_INTS_OFFSET         = 0x00000134
PIO_IRQ1_INTE_OFFSET         = 0x00000138
PIO_IRQ1_INTF_OFFSET         = 0x0000013c
PIO_IRQ1_INTS_OFFSET         = 0x00000140

# DMA: RP2040 datasheet 2.5.7
DMA_CTRL_TRIG_FIELDS = {
    "AHB_ERROR":   31<<BF_POS | 1<<BF_LEN | BFUINT32,
    "READ_ERROR":  30<<BF_POS | 1<<BF_LEN | BFUINT32,
    "WRITE_ERROR": 29<<BF_POS | 1<<BF_LEN | BFUINT32,
    "BUSY":        24<<BF_POS | 1<<BF_LEN | BFUINT32,
    "SNIFF_EN":    23<<BF_POS | 1<<BF_LEN | BFUINT32,
    "BSWAP":       22<<BF_POS | 1<<BF_LEN | BFUINT32,
    "IRQ_QUIET":   21<<BF_POS | 1<<BF_LEN | BFUINT32,
    "TREQ_SEL":    15<<BF_POS | 6<<BF_LEN | BFUINT32,
    "CHAIN_TO":    11<<BF_POS | 4<<BF_LEN | BFUINT32,
    "RING_SEL":    10<<BF_POS | 1<<BF_LEN | BFUINT32,
    "RING_SIZE":    6<<BF_POS | 4<<BF_LEN | BFUINT32,
    "INCR_WRITE":   5<<BF_POS | 1<<BF_LEN | BFUINT32,
    "INCR_READ":    4<<BF_POS | 1<<BF_LEN | BFUINT32,
    "DATA_SIZE":    2<<BF_POS | 2<<BF_LEN | BFUINT32,
    "HIGH_PRIORITY":1<<BF_POS | 1<<BF_LEN | BFUINT32,
    "EN":           0<<BF_POS | 1<<BF_LEN | BFUINT32
}
# Channel-specific DMA registers
DMA_CHAN_REGS = {
    "READ_ADDR_REG":       0x00|UINT32,
    "WRITE_ADDR_REG":      0x04|UINT32,
    "TRANS_COUNT_REG":     0x08|UINT32,
    "CTRL_TRIG_REG":       0x0c|UINT32,
    "CTRL_TRIG":          (0x0c,DMA_CTRL_TRIG_FIELDS)
}
# General DMA registers
DMA_REGS = {
    "INTR":               0x400|UINT32,
    "INTE0":              0x404|UINT32,
    "INTF0":              0x408|UINT32,
    "INTS0":              0x40c|UINT32,
    "INTE1":              0x414|UINT32,
    "INTF1":              0x418|UINT32,
    "INTS1":              0x41c|UINT32,
    "TIMER0":             0x420|UINT32,
    "TIMER1":             0x424|UINT32,
    "TIMER2":             0x428|UINT32,
    "TIMER3":             0x42c|UINT32,
    "MULTI_CHAN_TRIGGER": 0x430|UINT32,
    "SNIFF_CTRL":         0x434|UINT32,
    "SNIFF_DATA":         0x438|UINT32,
    "FIFO_LEVELS":        0x440|UINT32,
    "CHAN_ABORT":         0x444|UINT32
}

# GPIO status and control: RP2040 datasheet 2.19.6.1.10
GPIO_STATUS_FIELDS = {
    "IRQTOPROC":  26<<BF_POS | 1<<BF_LEN | BFUINT32,
    "IRQFROMPAD": 24<<BF_POS | 1<<BF_LEN | BFUINT32,
    "INTOPERI":   19<<BF_POS | 1<<BF_LEN | BFUINT32,
    "INFROMPAD":  17<<BF_POS | 1<<BF_LEN | BFUINT32,
    "OETOPAD":    13<<BF_POS | 1<<BF_LEN | BFUINT32,
    "OEFROMPERI": 12<<BF_POS | 1<<BF_LEN | BFUINT32,
    "OUTTOPAD":    9<<BF_POS | 1<<BF_LEN | BFUINT32,
    "OUTFROMPERI": 8<<BF_POS | 1<<BF_LEN | BFUINT32
}
GPIO_CTRL_FIELDS = {
    "IRQOVER":    28<<BF_POS | 2<<BF_LEN | BFUINT32,
    "INOVER":     16<<BF_POS | 2<<BF_LEN | BFUINT32,
    "OEOVER":     12<<BF_POS | 2<<BF_LEN | BFUINT32,
    "OUTOVER":     8<<BF_POS | 2<<BF_LEN | BFUINT32,
    "FUNCSEL":     0<<BF_POS | 5<<BF_LEN | BFUINT32
}
GPIO_REGS = {
    "GPIO_STATUS_REG":     0x00|UINT32,
    "GPIO_STATUS":        (0x00,GPIO_STATUS_FIELDS),
    "GPIO_CTRL_REG":       0x04|UINT32,
    "GPIO_CTRL":          (0x04,GPIO_CTRL_FIELDS)
}

# PAD control: RP2040 datasheet 2.19.6.3
PAD_FIELDS = {
    "OD":          7<<BF_POS | 1<<BF_LEN | BFUINT32,
    "IE":          6<<BF_POS | 1<<BF_LEN | BFUINT32,
    "DRIVE":       4<<BF_POS | 2<<BF_LEN | BFUINT32,
    "PUE":         3<<BF_POS | 1<<BF_LEN | BFUINT32,
    "PDE":         2<<BF_POS | 1<<BF_LEN | BFUINT32,
    "SCHMITT":     1<<BF_POS | 1<<BF_LEN | BFUINT32,
    "SLEWFAST":    0<<BF_POS | 1<<BF_LEN | BFUINT32
}
PAD_REGS = {
    "PAD_REG":             0x00|UINT32,
    "PAD":                (0x00,PAD_FIELDS)
}

# ADC: RP2040 datasheet 4.9.6
ADC_CS_FIELDS = {
    "RROBIN":     16<<BF_POS | 5<<BF_LEN | BFUINT32,
    "AINSEL":     12<<BF_POS | 3<<BF_LEN | BFUINT32,
    "ERR_STICKY": 10<<BF_POS | 1<<BF_LEN | BFUINT32,
    "ERR":         9<<BF_POS | 1<<BF_LEN | BFUINT32,
    "READY":       8<<BF_POS | 1<<BF_LEN | BFUINT32,
    "START_MANY":  3<<BF_POS | 1<<BF_LEN | BFUINT32,
    "START_ONCE":  2<<BF_POS | 1<<BF_LEN | BFUINT32,
    "TS_EN":       1<<BF_POS | 1<<BF_LEN | BFUINT32,
    "EN":          0<<BF_POS | 1<<BF_LEN | BFUINT32
}
ADC_FCS_FIELDS = {
    "THRESH":     24<<BF_POS | 4<<BF_LEN | BFUINT32,
    "LEVEL":      16<<BF_POS | 4<<BF_LEN | BFUINT32,
    "OVER":       11<<BF_POS | 1<<BF_LEN | BFUINT32,
    "UNDER":      10<<BF_POS | 1<<BF_LEN | BFUINT32,
    "FULL":        9<<BF_POS | 1<<BF_LEN | BFUINT32,
    "EMPTY":       8<<BF_POS | 1<<BF_LEN | BFUINT32,
    "DREQ_EN":     3<<BF_POS | 1<<BF_LEN | BFUINT32,
    "ERR":         2<<BF_POS | 1<<BF_LEN | BFUINT32,
    "SHIFT":       1<<BF_POS | 1<<BF_LEN | BFUINT32,
    "EN":          0<<BF_POS | 1<<BF_LEN | BFUINT32,
}
ADC_REGS = {
    "CS_REG":              0x00|UINT32,
    "CS":                 (0x00,ADC_CS_FIELDS),
    "RESULT_REG":          0x04|UINT32,
    "FCS_REG":             0x08|UINT32,
    "FCS":                (0x08,ADC_FCS_FIELDS),
    "FIFO_REG":            0x0c|UINT32,
    "DIV_REG":             0x10|UINT32,
    "INTR_REG":            0x14|UINT32,
    "INTE_REG":            0x18|UINT32,
    "INTF_REG":            0x1c|UINT32,
    "INTS_REG":            0x20|UINT32
}

DREQ_PIO0_TX0 = 0x0
DREQ_PIO0_TX1 = 0x1
DREQ_PIO0_TX2 = 0x2
DREQ_PIO0_TX3 = 0x3
DREQ_PIO0_RX0 = 0x4
DREQ_PIO0_RX1 = 0x5
DREQ_PIO0_RX2 = 0x6
DREQ_PIO0_RX3 = 0x7
DREQ_PIO1_TX0 = 0x8
DREQ_PIO1_TX1 = 0x9
DREQ_PIO1_TX2 = 0xa
DREQ_PIO1_TX3 = 0xb
DREQ_PIO1_RX0 = 0xc
DREQ_PIO1_RX1 = 0xd
DREQ_PIO1_RX2 = 0xe
DREQ_PIO1_RX3 = 0xf

DREQ_SPI0_TX,  DREQ_SPI0_RX  = 16, 17
DREQ_SPI1_TX,  DREQ_SPI1_RX,  DREQ_UART0_TX = 18, 19, 20
DREQ_UART0_RX, DREQ_UART1_TX, DREQ_UART1_RX = 21, 22, 23
DREQ_I2C0_TX,  DREQ_I2C0_RX,  DREQ_I2C1_TX  = 32, 33, 34
DREQ_I2C1_RX,  DREQ_ADC                     = 35, 36

DMA_CHANS = [struct(DMA_BASE + n*DMA_CHAN_WIDTH, DMA_CHAN_REGS) for n in range(0,DMA_CHAN_COUNT)]
DMA_DEVICE = struct(DMA_BASE, DMA_REGS)
GPIO_PINS = [struct(IO_BANK0_BASE + n*GPIO_CHAN_WIDTH, GPIO_REGS) for n in range(0,GPIO_PIN_COUNT)]
PAD_PINS =  [struct(PADS_BANK0_BASE + n*PAD_PIN_WIDTH, PAD_REGS) for n in range(0,GPIO_PIN_COUNT)]

GPIO_FUNC_SPI, GPIO_FUNC_UART, GPIO_FUNC_I2C = 1, 2, 3
GPIO_FUNC_PWM, GPIO_FUNC_SIO, GPIO_FUNC_PIO0 = 4, 5, 6
GPIO_FUNC_NULL = 0x1f

# EOF