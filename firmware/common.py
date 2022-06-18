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

import time

LED_BLINK_TIME_MS = 250
WRITE_WAIT_TIMEOUT_MS = 1200  # Datasheet says block erase takes max 1s, add margin

ERR_OK = 0
ERR_WRONG_CARD = 1
ERR_WRONG_FLASH_ID = 2
ERR_TIMEOUT = 3

def wait_write_complete(flash, timeout_ms):
    start_time = time.ticks_ms()
    # Wait while WIP and WEL bits are set
    while (flash.rdsr() & 0x03) != 0:
        curr_time = time.ticks_ms()
        if time.ticks_diff(curr_time, start_time) > timeout_ms:
            # Timeout exceeded
            return False

    # Completed within timeout
    return True
