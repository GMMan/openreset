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

from hashlib import sha256
from binascii import hexlify

from md5 import md5
from spi_flash import SPIFlashDriver, MX25LDriver
import common

class DimResetter:
    ID_HASH = b'\xb2\xdc\xb5\x07\x7c\x68\xd2\xd5\x40\xde\x10\x45\x9a\x06\x18\x23\x2a\x21\x17\xd3\x48\xac\x10\xf2\x89\x8f\xb1\x5c\x61\x46\x84\x82'
    FLASH_ID = b'\xc2\x20\x16'  # MX25L3233F
    ERASE_ADDRS = [0x10000, 0x90000, 0xa0000]

    def __init__(self, spi, cs) -> None:
        self.flash = MX25LDriver(spi, cs)

    def do_reset(self):
        print('Starting process')

        # Remove block protection
        sr = self.flash.rdsr()
        cr = self.flash.rdcr()
        # Unset BP0-3
        sr &= 0x40  # Retain QE, ignore WEL and WIP, unset all other bits
        self.flash.wren()
        self.flash.wrsr(sr, cr)
        if not common.wait_write_complete(self.flash, common.WRITE_WAIT_TIMEOUT_MS):
            print('Write timeout when removing write protection')
            return common.ERR_TIMEOUT

        # Erase blocks
        for addr in self.ERASE_ADDRS:
            self.flash.wren()
            self.flash.be(addr)
            if not common.wait_write_complete(self.flash, common.WRITE_WAIT_TIMEOUT_MS):
                print('Write timeout while erasing block address 0x{:06x}'.format(addr))
                return common.ERR_TIMEOUT

        # Reprotect blocks
        sr = self.flash.rdsr()
        cr = self.flash.rdcr()
        # Set BP0-3
        sr |= 0x3c
        self.flash.wren()
        self.flash.wrsr(sr, cr)
        if not common.wait_write_complete(self.flash, common.WRITE_WAIT_TIMEOUT_MS):
            print('Write timeout when setting write protection')
            # Not critical, so we won't return an error

        # Done!
        print('Process complete')
        return common.ERR_OK

    @classmethod
    def detect(cls, spi, cs):
        # Read and verify this is the correct type of card
        flash = MX25LDriver(spi, cs)
        id_data = flash.read(0x10, 0x22)
        hasher = sha256(id_data)
        hash_bytes = hasher.digest()
        if hash_bytes != cls.ID_HASH:
            # print('Card type check failed. Read data:')
            # print(hexlify(id_data))
            return common.ERR_WRONG_CARD

        # Check flash ID
        flash_id = flash.rdid()
        if flash_id != cls.FLASH_ID:
            # print('Flash ID didn\'t match. Read ID:')
            # print(hexlify(flash_id))
            return common.ERR_WRONG_FLASH_ID

        return common.ERR_OK


class TamaSmaCardResetter:
    ID_HASH = b'\x12\xef\xbb\x0a\xd7\x93\xd7\xd0\xd2\x16\xda\xdb\x30\x14\x66\xa2\xc3\xd0\xb1\xb1\x77\x7c\xcd\x9b\xfe\x4d\x29\xd2\xc7\x7a\x7f\xba'

    def __init__(self, spi, cs) -> None:
        self.flash = SPIFlashDriver(spi, cs)

    def do_reset(self):
        print('Starting process')

        # Read header
        header = bytearray(self.flash.read(0x0, 0x100))
        # Clear locks
        header[0x04:0x10] = b'\0' * 12
        # Recalculate checksum
        hash = md5(header[0x00:0x40])
        header[0x40:0x50] = hash.to_bytes(16, 'little')
        # Clear rest of the page with zeroes
        header[0x50:0x100] = b'\0' * 0xb0

        # Erase sector
        self.flash.wren()
        self.flash.se(0x0)
        if not common.wait_write_complete(self.flash, common.WRITE_WAIT_TIMEOUT_MS):
            print('Write timeout while erasing header sector')
            return common.ERR_TIMEOUT

        # Program header page
        self.flash.wren()
        self.flash.pp(0x0, header)
        if not common.wait_write_complete(self.flash, common.WRITE_WAIT_TIMEOUT_MS):
            print('Write timeout while programming header')
            return common.ERR_TIMEOUT

        # Clear entire page with zeroes and program to rest of sector
        header = bytearray(0x100)
        for i in range(0x100, 0x1000, 0x100):
            self.flash.wren()
            self.flash.pp(i, header)
            if not common.wait_write_complete(self.flash, common.WRITE_WAIT_TIMEOUT_MS):
                print('Write timeout while programming page 0x{:06x}'.format(i))
                return common.ERR_TIMEOUT

        # Done!
        print('Process complete')
        return common.ERR_OK

    @classmethod
    def detect(cls, spi, cs):
        # Read and verify this is the correct type of card
        flash = SPIFlashDriver(spi, cs)
        id_data = flash.read(0x10, 0x22)
        hasher = sha256(id_data)
        hash_bytes = hasher.digest()
        if hash_bytes != cls.ID_HASH:
            # print('Card type check failed. Read data:')
            # print(hexlify(id_data))
            return common.ERR_WRONG_CARD

        return common.ERR_OK


class PreDataMemoryResetter:
    ID_HASH = b'\xda\x15\x3a\x43\x7d\x99\xe0\x78\x91\xfc\xc7\x73\x46\xd6\x7a\x0c\xde\x9c\x75\xa1\x44\x80\x28\x37\x01\xc8\xe2\x8b\x51\xa6\x0b\x74'
    FLASH_ID = b'\xc8\x40\x14'  # GD25Q80E
    ERASE_ADDRS = [0xfd000, 0xfe000, 0xff000]

    def __init__(self, spi, cs) -> None:
        self.flash = SPIFlashDriver(spi, cs)

    def do_reset(self):
        print('Starting process')

        # Erase pages
        for addr in self.ERASE_ADDRS:
            self.flash.wren()
            self.flash.se(addr)
            if not common.wait_write_complete(self.flash, common.WRITE_WAIT_TIMEOUT_MS):
                print('Write timeout while erasing page address 0x{:06x}'.format(addr))
                return common.ERR_TIMEOUT

        # Clear lock sectors with zeroes
        zeros = bytearray(0x100)
        for i in range(0xfd000, 0x100000, 0x100):
            self.flash.wren()
            self.flash.pp(i, zeros)
            if not common.wait_write_complete(self.flash, common.WRITE_WAIT_TIMEOUT_MS):
                print('Write timeout while programming page 0x{:06x}'.format(i))
                return common.ERR_TIMEOUT

        # Done!
        print('Process complete')
        return common.ERR_OK

    @classmethod
    def detect(cls, spi, cs):
        # Read and verify this is the correct type of card
        flash = SPIFlashDriver(spi, cs)
        id_data = flash.read(0x10, 0x20)
        hasher = sha256(id_data)
        hash_bytes = hasher.digest()
        if hash_bytes != cls.ID_HASH:
            # print('Card type check failed. Read data:')
            # print(hexlify(id_data))
            return common.ERR_WRONG_CARD

        # Check flash ID
        flash_id = flash.rdid()
        if flash_id != cls.FLASH_ID:
            # print('Flash ID didn\'t match. Read ID:')
            # print(hexlify(flash_id))
            return common.ERR_WRONG_FLASH_ID

        return common.ERR_OK
