import struct
class BitBuffer:
    def __init__(self, debug=True):
        self.bits = []
        self.debug = debug
        self.debug_log = [] if debug else None

    def write_method_15(self, flag: bool):
        self.write_method_11(1 if flag else 0, 1)
        if self.debug:
            self.debug_log.append(f"method_15={flag}")

    def to_bytes(self):
        while len(self.bits) % 8 != 0:
            self.bits.append(0)
            if self.debug:
                self.debug_log.append("pad_to_byte=0")
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            byte = 0
            for bit in self.bits[i:i + 8]:
                byte = (byte << 1) | bit
            out.append(byte)
        return bytes(out)

    def write_method_20(self, bit_count: int, value: int):
        while bit_count > 0:
            byte_index = len(self.bits) // 8
            bit_offset = len(self.bits) & 7
            bits_left_in_byte = 8 - bit_offset
            bits_to_write = min(bit_count, bits_left_in_byte)

            shift = bit_count - bits_to_write
            mask = (value >> shift) & ((1 << bits_to_write) - 1)

            for i in range(bits_to_write):
                self.bits.append((mask >> (bits_to_write - 1 - i)) & 1)

            bit_count -= bits_to_write

            if self.debug:
                self.debug_log.append(f"write_method_20: value={value}, bits_written={bits_to_write}")

    def write_method_739(self, value: int):
        if value < 0:
            self.write_method_11(1, 1)
            self.write_method_91(-value)
        else:
            self.write_method_11(0, 1)
            self.write_method_91(value)
        if self.debug:
            self.debug_log.append(f"method_739={value}")

    def write_method_4(self, val: int):
        bits_needed = val.bit_length() if val > 0 else 1
        bits_to_use = max(2, (bits_needed + 1) & ~1)
        prefix = (bits_to_use // 2) - 1
        assert 0 <= prefix <= 15, f"Value too large for method_4: {val}"
        self.write_method_11(prefix, 4)
        self.write_method_11(val, bits_to_use)
        if self.debug:
            self.debug_log.append(f"method_4={val}, prefix={prefix}, bits={bits_to_use}")

    def write_method_26(self, val: str):
        if val is None:
            val = ""
        encoded = val.encode('utf-8')
        length = min(len(encoded), 65535)
        self.write_method_11(length, 16)
        for byte in encoded[:length]:
            self.write_method_11(byte, 8)
        if self.debug:
            self.debug_log.append(f"method_26={val}, length={length}")

    def write_method_6(self, val: int, bit_count: int):
        self.write_method_11(val, bit_count)
        if self.debug:
            self.debug_log.append(f"method_6={val}, bits={bit_count}")

    def write_method_91(self, val: int):
        bits_needed = val.bit_length() if val > 0 else 1
        bits_to_use = max(2, (bits_needed + 1) & ~1)
        n = (bits_to_use // 2) - 1
        self.write_method_11(n, 3)
        self.write_method_11(val, bits_to_use)
        if self.debug:
            self.debug_log.append(f"method_91={val}, n={n}, bits={bits_to_use}")

    def write_method_9(self, val: int):
        bitlen = val.bit_length()
        if bitlen % 2:
            bitlen += 1
        prefix = (bitlen // 2) - 1
        self.write_method_11(prefix, 4)
        self.write_method_11(val, bitlen)

    def write_method_45(self, val: int):
        if val < 0:
            self.write_method_11(1, 1)
            self.write_method_4(-val)
        else:
            self.write_method_11(0, 1)
            self.write_method_4(val)
        if self.debug:
            self.debug_log.append(f"method_45={val}, sign={1 if val < 0 else 0}")

    def write_method_11(self, value, bit_count):
        if self.debug:
            self.debug_log.append(f"write_method_6={value:0{bit_count}b} ({bit_count} bits)")
        for i in reversed(range(bit_count)):
            self.bits.append((value >> i) & 1)

    def write_method_393(self, val):
        self.write_method_11(val & 0xFF, 8)

    def write_method_13(self, *vals: str):
        val = " ".join(str(v) for v in vals)
        encoded = val.encode('utf-8')
        length = min(len(encoded), 65535)

        self.write_method_11(length, 16)
        for byte in encoded[:length]:
            self.write_method_11(byte, 8)

        if self.debug:
            self.debug_log.append(f"method_13={val}, length={length}")

    def write_float(self, val: float):
        b = struct.pack(">f", val)
        for byte in b:
            self.write_method_11(byte, 8)

    def write_method_309(self, val: float):
        self.write_float(val)
        if self.debug:
            self.debug_log.append(f"method_309={val}")

    def write_method_24(self, val: int):
        """
        Write a signed integer as a 1-bit sign flag followed by the magnitude via method_9.
        - val: Signed integer to write.
        """
        sign = 1 if val < 0 else 0
        self.write_method_11(sign, 1)
        self.write_method_9(abs(val))
        if self.debug:
            self.debug_log.append(f"method_24={val}, sign={sign}")

    def get_debug_log(self):
        return self.debug_log if self.debug else []
