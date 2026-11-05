"""Synthetic UART ONLY, including hostile-output and scrollback test fixtures."""

import os
import tty

tty.setraw(0)
os.write(1, b"SYNTHETIC_UART_READY\r\n")
seen = b""
while True:
    value = os.read(0, 1024)
    if not value:
        break
    os.write(1, value)
    seen = (seen + value)[-128:]
    if b"MOCK_ANSI" in seen:
        os.write(
            1,
            b"\x1b[31mANSI_RED_PROOF\x1b[0m\r\n\x1b]52;c;Tk9UX0FMTE9XRUQ=\x07\x1b]8;;https://example.invalid/\x07HOSTILE_LINK\x1b]8;;\x07\r\n",
        )
        seen = b""
    if b"MOCK_LINES" in seen:
        os.write(1, b"SCROLLBACK_OLD_CANARY\r\n")
        for n in range(10050):
            os.write(1, f"SYNTHETIC_LINE_{n:05d}\r\n".encode())
        os.write(1, b"SCROLLBACK_FINAL_PROOF\r\n")
        seen = b""
