"""Synthetic UART with concurrent keystroke echo; no hardware access."""

import os
import tty

tty.setraw(0)
os.write(1, b"SYNTHETIC_UART_READY\r\n")
while True:
    value = os.read(0, 1024)
    if not value:
        break
    os.write(1, b"UART:" + value + b"\r\n")
