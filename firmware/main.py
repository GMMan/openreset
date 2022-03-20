# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of OpenReset.
#
# Copyright (C) 2022  cyanic
#
# OpenReset is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenReset is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OpenReset.  If not, see <https://www.gnu.org/licenses/>.

import machine
import time
from mx25l import MX25LDriver
from binascii import hexlify
from hashlib import sha256

# Hardware definitions ========================================================

# LEDs
led_green = machine.Pin(25, machine.Pin.OUT)
led_red = machine.Pin(1, machine.Pin.OUT)

# Card detect
card_detect = machine.Pin(20, machine.Pin.IN, machine.Pin.PULL_UP)

# SPI
spi_sck = machine.Pin(18)
spi_mosi = machine.Pin(19)
spi_miso = machine.Pin(16)
spi_cs = machine.Pin(17, machine.Pin.OUT)

spi = machine.SPI(0, baudrate=2_000_000, sck=spi_sck, mosi=spi_mosi,
                  miso=spi_miso)

flash = MX25LDriver(spi, spi_cs)

# Main logic ==================================================================

ID_HASH = b'\xb2\xdc\xb5\x07\x7c\x68\xd2\xd5\x40\xde\x10\x45\x9a\x06\x18\x23\x2a\x21\x17\xd3\x48\xac\x10\xf2\x89\x8f\xb1\x5c\x61\x46\x84\x82'
FLASH_ID = b'\xc2\x20\x16'  # MX25L3233F
WRITE_WAIT_TIMEOUT_MS = 1200  # Datasheet says block erase takes max 1s, add margin
ERASE_ADDRS = [0x10000, 0x90000, 0xa0000]
LED_BLINK_TIME_MS = 250

ERR_OK = 0
ERR_WRONG_CARD = 1
ERR_WRONG_FLASH_ID = 2
ERR_TIMEOUT = 3

def wait_write_complete(timeout_ms):
    start_time = time.ticks_ms()
    # Wait while WIP and WEL bits are set
    while (flash.rdsr() & 0x03) != 0:
        curr_time = time.ticks_ms()
        if time.ticks_diff(curr_time, start_time) > timeout_ms:
            # Timeout exceeded
            return False

    # Completed within timeout
    return True

def do_erase():
    print('Starting process')

    # Read and verify this is the correct type of card
    id_data = flash.read(0x10, 0x22)
    hasher = sha256(id_data)
    hash_bytes = hasher.digest()
    if hash_bytes != ID_HASH:
        print('Card type check failed. Read data:')
        print(hexlify(id_data))
        return ERR_WRONG_CARD

    # Check flash ID
    flash_id = flash.rdid()
    if flash_id != FLASH_ID:
        print('Flash ID didn\'t match. Read ID:')
        print(hexlify(flash_id))
        return ERR_WRONG_FLASH_ID

    # Remove block protection
    sr = flash.rdsr()
    cr = flash.rdcr()
    # Unset BP0-3
    sr &= 0x40  # Retain QE, ignore WEL and WIP, unset all other bits
    flash.wren()
    flash.wrsr(sr, cr)
    if not wait_write_complete(WRITE_WAIT_TIMEOUT_MS):
        print('Write timeout when removing write protection')
        return ERR_TIMEOUT

    # Erase blocks
    for addr in ERASE_ADDRS:
        flash.wren()
        flash.be(addr)
        if not wait_write_complete(WRITE_WAIT_TIMEOUT_MS):
            print('Write timeout while erasing address 0x{:06x}'.format(addr))
            return ERR_TIMEOUT

    # Reprotect blocks
    sr = flash.rdsr()
    cr = flash.rdcr()
    # Set BP0-3
    sr |= 0x3c
    flash.wren()
    flash.wrsr(sr, cr)
    if not wait_write_complete(WRITE_WAIT_TIMEOUT_MS):
        print('Write timeout when setting write protection')
        # Not critical, so we won't return an error

    # Done!
    print('Process complete')
    return ERR_OK

def blink_err(times):
    # Blink off
    for _ in range(times):
        led_red.value(0)
        time.sleep_ms(LED_BLINK_TIME_MS)
        led_red.value(1)
        time.sleep_ms(LED_BLINK_TIME_MS)

# Main loop ===================================================================

# Red LED on by default to indicate power
led_red.value(1)
led_green.value(0)

while True:
    # Wait until card is inserted (reads low)
    while card_detect.value() != 0:
        time.sleep_ms(50)

    # Light LED to indicate we are running
    led_green.value(1)
    print('Card inserted')
    # Wait a bit in case card is still being inserted
    time.sleep_ms(200)

    # Let's go!
    ret = do_erase()

    # Done, extinguish LED
    led_green.value(0)

    if ret != ERR_OK:
        # Blink error until card removed
        while card_detect.value() == 0:
            blink_err(ret)
            time.sleep_ms(1000)
    else:
        # Wait until card is removed (reads high)
        while card_detect.value() == 0:
            time.sleep_ms(50)
    print('Card removed')
