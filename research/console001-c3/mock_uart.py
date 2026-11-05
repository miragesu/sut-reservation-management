"""Synthetic UART equivalent: echoes bytes; stores only an input byte counter."""
import os
from pathlib import Path
import sys
import tty

tty.setraw(0)
counter = Path(sys.argv[1])
total = 0
counter.write_text('0')
os.write(1, b'MOCK_READY\r\n')
while True:
    data = os.read(0, 4096)
    if not data:
        break
    total += len(data)
    counter.write_text(str(total))
    os.write(1, b'UART:' + data.hex().encode() + b'\r\n')
