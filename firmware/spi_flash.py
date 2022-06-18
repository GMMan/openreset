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

class SPIFlashDriver:
    """
    Base SPI NOR flash driver, can be used as a generic driver.
    """
    def __init__(self, spi, cs):
        self.spi = spi
        self.cs = cs

    def rdid(self):
        """Read and return device ID."""
        self.cs.value(0)
        self.spi.write(b'\x9f')
        resp = self.spi.read(3)
        self.cs.value(1)
        return resp

    def rdsr(self):
        """Read and return the status register (only first byte)."""
        self.cs.value(0)
        self.spi.write(b'\x05')
        resp = self.spi.read(1)[0]
        self.cs.value(1)
        return resp

    def wren(self):
        """Set write enable latch."""
        self.cs.value(0)
        self.spi.write(b'\x06')
        self.cs.value(1)

    def read(self, addr, count):
        """Read and return bytes from flash array."""
        self.cs.value(0)
        self.spi.write(bytes([0x03, (addr >> 16) & 0xff, (addr >> 8) & 0xff,
                              addr & 0xff]))
        resp = self.spi.read(count)
        self.cs.value(1)
        return resp

    def pp(self, addr, data):
        """Program a page."""
        self.cs.value(0)
        self.spi.write(bytes([0x02, (addr >> 16) & 0xff, (addr >> 8) & 0xff,
                              addr & 0xff]))
        self.spi.write(data)
        self.cs.value(1)

    def be(self, addr):
        """Erase 64KB block."""
        self.cs.value(0)
        self.spi.write(bytes([0xd8, (addr >> 16) & 0xff, (addr >> 8) & 0xff,
                              addr & 0xff]))
        self.cs.value(1)

    def se(self, addr):
        """Erase 4KB sector."""
        self.cs.value(0)
        self.spi.write(bytes([0x20, (addr >> 16) & 0xff, (addr >> 8) & 0xff,
                              addr & 0xff]))
        self.cs.value(1)


class MX25LDriver(SPIFlashDriver):
    """
    Macronix MX25L* SPI NOR flash driver
    """
    def rdcr(self):
        """Read and return the configuration register."""
        self.cs.value(0)
        self.spi.write(b'\x15')
        resp = self.spi.read(1)[0]
        self.cs.value(1)
        return resp

    def wrsr(self, sr, cr):
        """Write the status and configuration registers."""
        self.cs.value(0)
        self.spi.write(bytes([0x01, sr, cr]))
        self.cs.value(1)
