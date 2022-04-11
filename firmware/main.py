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
import struct

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

flash = MX25LDriver(spi, spi_cs)

# Main logic ==================================================================

ID_HASH = b'\xb2\xdc\xb5\x07\x7c\x68\xd2\xd5\x40\xde\x10\x45\x9a\x06\x18\x23\x2a\x21\x17\xd3\x48\xac\x10\xf2\x89\x8f\xb1\x5c\x61\x46\x84\x82'
FLASH_ID = b'\xc2\x20\x16'  # MX25L3233F
WRITE_WAIT_TIMEOUT_MS = 1200  # Datasheet says block erase takes max 1s, add margin
LED_BLINK_TIME_MS = 250

ERR_OK = 0
ERR_WRONG_CARD = 1
ERR_WRONG_FLASH_ID = 2
ERR_TIMEOUT = 3
ERR_NO_PATCHES = 4
ERR_ORIG_CHECKSUM_MISMATCH = 5
ERR_DIFF_CARD = 6

PATCHES = {
    21: {
        'orig_checksum': 0x7cf8,
        'new_checksum': 0x7cf9,
        'pages': [
            {
                'base': 0x030000,
                'bytes': [
                    {
                        'offset': 0x5c,
                        'patched': b'\xdc\xff'
                    }
                ]
            },
            {
                'base': 0x030100,
                'bytes': [
                    {
                        'offset': 0x04,
                        'patched': b'\x00\x00'
                    }
                ]
            },
        ]
    },
    22: {
        'orig_checksum': 0x54cb,
        'new_checksum': 0x54cc,
        'pages': [
            {
                'base': 0x030000,
                'bytes': [
                    {
                        'offset': 0x5c,
                        'patched': b'\xdc\xff'
                    }
                ]
            },
            {
                'base': 0x030100,
                'bytes': [
                    {
                        'offset': 0x04,
                        'patched': b'\x00\x00'
                    }
                ]
            },
        ]
    }
}

curr_backup_context = None


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


def generate_patch_sectors(patch_set):
    """
    Buckets patches into sectors

    We need to erase a full sector, so this helps keep track of the sectors we
    have and lets us read and patch on a whole-sector basis.
    """
    sectors = []

    # Assume patches are all in address order
    base_sector = 0
    curr_sector = None

    for page in patch_set['pages']:
        patch_base = page['base']
        if patch_base - base_sector >= 0x1000:
            if curr_sector is not None:
                sectors.append(curr_sector)
            base_sector = patch_base & ~0xfff
            curr_sector = {
                'base': base_sector,
                'pages': [],
                'buffer': None
            }
        curr_sector['pages'].append(page)

    if curr_sector is not None:
        sectors.append(curr_sector)
    
    return sectors


def do_patch():
    print('Starting process')
    global curr_backup_context

    # Read and verify this is the correct type of card
    id_data = flash.read(0x10, 0x22)
    hasher = sha256(id_data)
    hash_bytes = hasher.digest()
    if hash_bytes != ID_HASH:
        print('Card type check failed. Read data:')
        print(hexlify(id_data))
        return ERR_WRONG_CARD

    # Check card ID
    card_id = struct.unpack('<H', flash.read(0x32, 2))[0] ^ 0xffff
    if card_id not in PATCHES:
        return ERR_NO_PATCHES

    # Check flash ID
    flash_id = flash.rdid()
    if flash_id != FLASH_ID:
        print('Flash ID didn\'t match. Read ID:')
        print(hexlify(flash_id))
        return ERR_WRONG_FLASH_ID

    # Prepare patch session
    if curr_backup_context is None:
        # Verify checksum
        # Note: patch values are not XORed, so don't XOR here
        checksum = struct.unpack('<H', flash.read(0x3ffffe, 2))[0]
        if checksum != PATCHES[card_id]['orig_checksum']:
            print('Pre-patch card checksum does not match what\'s specified in patch')
            return ERR_ORIG_CHECKSUM_MISMATCH

        curr_backup_context = {
            'card_id': card_id,
            'index': 0,
            'sectors': generate_patch_sectors(PATCHES[card_id])
        }
    else:
        # Verify we're the same card
        if card_id != curr_backup_context['card_id']:
            print('This isn\'t the same card we were working on before')
            return ERR_DIFF_CARD
        
        # Verify checksum
        checksum = struct.unpack('<H', flash.read(0x3ffffe, 2))[0]
        if checksum != PATCHES[card_id]['orig_checksum']:
            print('Pre-patch card checksum does not match what\'s specified in patch')
            return ERR_ORIG_CHECKSUM_MISMATCH

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
    
    for i in range(curr_backup_context['index'], len(curr_backup_context['sectors'])):
        curr_backup_context['index'] = i
        curr_sector = curr_backup_context['sectors'][i]
        sector_base = curr_sector['base']

        if curr_sector['buffer'] is None:
            buffer = bytearray(flash.read(sector_base, 0x1000))
            curr_sector['buffer'] = buffer

            # Apply all patches to buffer
            for page in curr_sector['pages']:
                buffer_base = page['base'] - sector_base
                for patch in page['bytes']:
                    patch_base = buffer_base + patch['offset']
                    buffer[patch_base:patch_base + len(patch['patched'])] = patch['patched']
            
        # Erase sector
        flash.wren()
        flash.se(sector_base)
        if not wait_write_complete(WRITE_WAIT_TIMEOUT_MS):
            print('Write timeout while erasing sector 0x{:06x}'.format(sector_base))
            return ERR_TIMEOUT

        # Write patched pages
        for j in range(0, 0x1000, 0x100):
            flash.wren()
            flash.pp(sector_base + j, curr_sector['buffer'][j:j + 0x100])
            if not wait_write_complete(WRITE_WAIT_TIMEOUT_MS):
                print('Write timeout while writing page 0x{:06x}'.format(sector_base + j))
                return ERR_TIMEOUT
    
    # Update checksum
    # Erase sector
    flash.wren()
    flash.se(0x3ff000)
    if not wait_write_complete(WRITE_WAIT_TIMEOUT_MS):
        print('Write timeout while erasing sector 0x{:06x}'.format(sector_base))
        return ERR_TIMEOUT

    # Write new checksum
    checksum_page = bytearray([0xff] * 256)
    checksum_page[254:256] = struct.pack('<H', PATCHES[card_id]['new_checksum'])
    flash.wren()
    flash.pp(0x3fff00, checksum_page)
    if not wait_write_complete(WRITE_WAIT_TIMEOUT_MS):
        print('Write timeout while writing checksum page 0x{:06x}'.format(0x3fff00))
        return ERR_TIMEOUT

    curr_backup_context = None

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
    ret = do_patch()

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
