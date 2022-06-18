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
import common

from resetters import *

# Hardware definitions ========================================================

# LEDs
led_green = machine.Pin(25, machine.Pin.OUT)
led_red = machine.Pin(4, machine.Pin.OUT)

# Card detect
card_detect = machine.Pin(20, machine.Pin.IN, machine.Pin.PULL_UP)

# SPI
spi_sck = machine.Pin(18)
spi_mosi = machine.Pin(19)
spi_miso = machine.Pin(16)
spi_cs = machine.Pin(17, machine.Pin.OUT)

spi = machine.SPI(0, baudrate=2_000_000, sck=spi_sck, mosi=spi_mosi,
                  miso=spi_miso)

resetters = [DimResetter, TamaSmaCardResetter, PreDataMemoryResetter]

def blink_err(times):
    # Blink off
    for _ in range(times):
        led_red.value(0)
        time.sleep_ms(common.LED_BLINK_TIME_MS)
        led_red.value(1)
        time.sleep_ms(common.LED_BLINK_TIME_MS)

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

    ret = common.ERR_WRONG_CARD

    # Iterate the resetters, and if detect OK, perform reset
    for resetter in resetters:
        print('Checking for {}'.format(resetter.__name__))
        ret = resetter.detect(spi, spi_cs)
        if ret == common.ERR_OK:
            print('Detected by {}'.format(resetter.__name__))
            resetter_inst = resetter(spi, spi_cs)
            ret = resetter_inst.do_reset()
            break

    # Done, extinguish LED
    led_green.value(0)

    if ret == common.ERR_WRONG_CARD:
        print('Card type unrecognized')

    if ret != common.ERR_OK:
        # Blink error until card removed
        while card_detect.value() == 0:
            blink_err(ret)
            time.sleep_ms(1000)
    else:
        # Wait until card is removed (reads high)
        while card_detect.value() == 0:
            time.sleep_ms(50)
    print('Card removed')
