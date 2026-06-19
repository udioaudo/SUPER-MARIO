"""CPU 2 KiB internal work RAM with address mirroring.

NES 2A03 CPU internal RAM:
  - Address range 0x0000–0x07FF (2048 bytes actual storage)
  - Address range 0x0800–0x1FFF mirrors 0x0000–0x07FF
  - Mirroring is automatic via addr % size
"""


class RAM:
    """Simulates the NES 2 KiB internal CPU RAM."""

    def __init__(self, size: int = 2048) -> None:
        """Allocate `size` bytes, initialized to zero."""
        self._size: int = size
        self._data: bytearray = bytearray(size)

    def read(self, addr: int) -> int:
        """Read 1 byte from `addr`, with automatic address mirroring via addr % size."""
        return self._data[addr % self._size]

    def write(self, addr: int, value: int) -> None:
        """Write `value` to `addr`, clamped to 8 bits, with address mirroring."""
        self._data[addr % self._size] = value & 0xFF
