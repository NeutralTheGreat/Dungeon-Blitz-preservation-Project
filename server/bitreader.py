import struct
from typing import List

class BitReader:
    def __init__(self, data: bytes, debug: bool = False):
        self.data = bytearray(data)
        self.bit_index = 0
        self.debug = debug
        self.debug_log: List[str] = [] if debug else []

    def align_to_byte(self):
        remainder = self.bit_index % 8
        if remainder:
            skip_bits = 8 - remainder
            for _ in range(skip_bits):
                self.read_bit()
            if self.debug:
                self.debug_log.append(f"align_to_byte=skipped {skip_bits} bits")

    def remaining_bits(self) -> int:
        """
        Server-only helper: return how many unread bits remain in the buffer.
        The Flash client does not expose an equivalent method; it always knows
        how many bits to read based on the packet type.
        """
        total_bits = len(self.data) * 8
        return max(0, total_bits - self.bit_index)

    def read_bit(self) -> int:
        byte_index = self.bit_index // 8
        bit_offset = self.bit_index & 7
        if byte_index >= len(self.data):
            raise ValueError("Not enough data to read bit")
        bit = (self.data[byte_index] >> (7 - bit_offset)) & 1
        self.bit_index += 1
        if self.debug:
            self.debug_log.append(f"read_bit={bit} at bit_index={self.bit_index-1}")
        return bit

    def read_method_15(self) -> bool:
        """Read a single boolean (1 bit) from the bitstream, matching client method_15."""
        bit = self.read_bit()
        if self.debug:
            self.debug_log.append(f"method_15={bool(bit)}")
        return bool(bit)

    def read_method_20(self, bit_count: int) -> int:
        """Read bit_count bits across byte boundaries, MSB-first."""
        val = 0
        while bit_count > 0:
            byte_index = self.bit_index // 8
            bit_offset = self.bit_index & 7
            bits_left_in_byte = 8 - bit_offset
            bits_to_read = min(bit_count, bits_left_in_byte)

            mask = (1 << bits_to_read) - 1
            shift = bits_left_in_byte - bits_to_read
            current_byte = self.data[byte_index]
            extracted = (current_byte >> shift) & mask

            val = (val << bits_to_read) | extracted
            self.bit_index += bits_to_read
            bit_count -= bits_to_read

            if self.debug:
                self.debug_log.append(
                    f"read_method_20: byte_index={byte_index}, bit_offset={bit_offset}, "
                    f"bits_to_read={bits_to_read}, extracted={extracted}, val={val}"
                )
        return val

    def read_method_739(self) -> int:
        sign = self.read_bit()
        prefix = self.read_method_20(3)
        bits_to_use = (prefix + 1) * 2
        magnitude = self.read_method_20(bits_to_use)
        return -magnitude if sign else magnitude

    def read_method_4(self) -> int:
        prefix = self.read_method_20(4)
        bits_to_use = (prefix + 1) * 2
        if self.bit_index + bits_to_use > len(self.data) * 8:
            raise ValueError(f"Not enough data to read {bits_to_use} bits for method_4")
        value = self.read_method_20(bits_to_use)
        if self.debug:
            self.debug_log.append(f"read_method_4={value}, prefix={prefix}, bits={bits_to_use}")
        return value

    def read_method_26(self) -> str:
        length = self.read_method_20(16)
        raw = bytearray(self.read_method_20(8) for _ in range(length))
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw.decode('latin-1', errors='replace')

    def read_method_706(self) -> int:
        is_negative = bool(self.read_bit())
        prefix = self.read_method_20(3)
        bit_length = (prefix + 1) * 2
        value = self.read_method_20(bit_length)
        return -value if is_negative else value

    def read_method_6(self, bit_count: int) -> int:
        if self.bit_index + bit_count > len(self.data) * 8:
            raise ValueError(f"Not enough data to read {bit_count} bits for method_6")
        value = self.read_method_20(bit_count)
        if self.debug:
            self.debug_log.append(f"read_method_6={value}, bits={bit_count}")
        return value

    def read_method_9(self) -> int:
        prefix = self.read_method_20(4)
        n_bits = (prefix + 1) * 2
        if self.bit_index + n_bits > len(self.data) * 8:
            raise ValueError(f"Not enough data to read {n_bits} bits for method_9")
        value = self.read_method_20(n_bits)
        if self.debug:
            self.debug_log.append(f"read_method_9={value}, prefix={prefix}, bits={n_bits}")
        return value

    def read_method_45(self) -> int:
        sign = self.read_bit()
        if self.bit_index + 4 > len(self.data) * 8:
            raise ValueError("Not enough data to read method_4 prefix for method_45")
        magnitude = self.read_method_4()
        value = -magnitude if sign else magnitude
        if self.debug:
            self.debug_log.append(f"read_method_45={value}, sign={sign}, magnitude={magnitude}")
        return value

    def read_method_393(self) -> int:
        value = self.read_method_20(8)
        if self.debug:
            self.debug_log.append(f"read_method_393={value}")
        return value

    def read_method_560(self) -> float:
        if self.bit_index + 32 > len(self.data) * 8:
            raise ValueError("Not enough data to read float")
        bits = self.read_method_20(32)
        bytes_val = struct.pack('>I', bits)
        float_val = struct.unpack('>f', bytes_val)[0]
        if self.debug:
            self.debug_log.append(f"read_method_560={float_val}")
        return float_val

    def read_method_13(self) -> str:
        length = self.read_method_20(16)
        if self.bit_index + length * 8 > len(self.data) * 8:
            raise ValueError("Not enough data to read string")
        result_bytes = bytearray()
        for _ in range(length):
            result_bytes.append(self.read_method_20(8))
        try:
            return result_bytes.decode('utf-8')
        except UnicodeDecodeError:
            return result_bytes.decode('latin1')

    def read_method_24(self) -> int:
        if self.bit_index + 1 > len(self.data) * 8:
            raise ValueError("Not enough data to read sign bit for method_24")
        sign = self.read_bit()
        magnitude = self.read_method_9()
        value = -magnitude if sign else magnitude
        if self.debug:
            self.debug_log.append(f"read_method_24={value}, sign={sign}, magnitude={magnitude}")
        return value

    def read_method_309(self) -> float:
        return self.read_float()

    def read_float(self) -> float:
        bits = self.read_method_20(32)
        bytes_val = struct.pack('>I', bits)
        return struct.unpack('>f', bytes_val)[0]

    def read_method_236(self) -> int:
        prefix = self.read_method_20(3)
        bits_to_use = (prefix + 1) * 2

        if self.bit_index + bits_to_use > len(self.data) * 8:
            raise ValueError("Not enough data to read method_236 value")

        return self.read_method_20(bits_to_use)

    def get_debug_log(self) -> List[str]:
        return self.debug_log