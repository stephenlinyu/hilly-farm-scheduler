"""Small dependency-free JT/T 808 (2011/2013 header) codec."""

from dataclasses import dataclass
from datetime import datetime
import threading


@dataclass(frozen=True)
class Jt808Message:
    message_id: int
    body_length: int
    sub_package: bool
    terminal_id: str
    serial_no: int
    body: bytes


class Jt808Codec:
    def __init__(self):
        self._platform_serial = 1
        self._serial_lock = threading.Lock()

    def decode(self, frame):
        frame = bytes(frame)
        if len(frame) < 2 or frame[0] != 0x7E or frame[-1] != 0x7E:
            raise ValueError("invalid JT808 frame boundary")

        data = self._unescape(frame[1:-1])
        if len(data) < 13:
            raise ValueError("JT808 frame is too short")

        expected = data[-1]
        actual = self.xor(data[:-1])
        if expected != actual:
            raise ValueError(f"JT808 checksum mismatch: expected={expected}, actual={actual}")

        message_id = self.read_word(data, 0)
        properties = self.read_word(data, 2)
        if properties & 0x4000:
            raise ValueError("JT808 2019 version header is not enabled for this terminal")
        body_length = properties & 0x03FF
        sub_package = bool(properties & 0x2000)
        terminal_id = self.decode_bcd(data, 4, 6)
        serial_no = self.read_word(data, 10)
        body_start = 16 if sub_package else 12
        if len(data) < body_start + body_length + 1:
            raise ValueError("JT808 body length is invalid")
        if sub_package:
            raise ValueError("JT808 sub-packages are not supported")

        return Jt808Message(
            message_id=message_id,
            body_length=body_length,
            sub_package=sub_package,
            terminal_id=terminal_id,
            serial_no=serial_no,
            body=data[body_start:body_start + body_length],
        )

    def encode_general_response(self, request, result=0):
        body = bytearray(5)
        self.write_word(body, 0, request.serial_no)
        self.write_word(body, 2, request.message_id)
        body[4] = result & 0xFF
        return self.encode(0x8001, request.terminal_id, self._next_platform_serial(), body)

    def encode_register_response(self, request, result=0, auth_code="123456"):
        auth_bytes = auth_code.encode("ascii") if result == 0 else b""
        body = bytearray(3 + len(auth_bytes))
        self.write_word(body, 0, request.serial_no)
        body[2] = result & 0xFF
        body[3:] = auth_bytes
        return self.encode(0x8100, request.terminal_id, self._next_platform_serial(), body)

    def encode(self, message_id, terminal_id, serial_no, body=b""):
        body = bytes(body)
        data = bytearray(12 + len(body) + 1)
        self.write_word(data, 0, message_id)
        self.write_word(data, 2, len(body))
        self.write_bcd(data, 4, 6, terminal_id)
        self.write_word(data, 10, serial_no)
        data[12:12 + len(body)] = body
        data[-1] = self.xor(data[:-1])
        return b"\x7e" + self._escape(data) + b"\x7e"

    @staticmethod
    def read_word(data, offset):
        return (data[offset] << 8) | data[offset + 1]

    @staticmethod
    def read_dword(data, offset):
        return int.from_bytes(data[offset:offset + 4], "big", signed=False)

    @staticmethod
    def write_word(data, offset, value):
        data[offset] = (value >> 8) & 0xFF
        data[offset + 1] = value & 0xFF

    @staticmethod
    def xor(data):
        value = 0
        for item in data:
            value ^= item
        return value

    @staticmethod
    def decode_bcd(data, offset, length):
        digits = "".join(f"{item:02x}" for item in data[offset:offset + length])
        if any(character not in "0123456789" for character in digits):
            raise ValueError("invalid BCD value")
        return digits.lstrip("0") or "0"

    def decode_bcd_time(self, data, offset):
        digits = "".join(f"{item:02x}" for item in data[offset:offset + 6])
        if len(digits) != 12 or any(character not in "0123456789" for character in digits):
            raise ValueError("invalid JT808 BCD time")
        value = datetime.strptime(digits, "%y%m%d%H%M%S")
        return value.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def write_bcd(data, offset, length, value):
        digits = "".join(character for character in str(value or "") if character.isdigit())
        digits = digits[-length * 2:].rjust(length * 2, "0")
        for index in range(length):
            data[offset + index] = int(digits[index * 2:index * 2 + 2], 16)

    def _next_platform_serial(self):
        with self._serial_lock:
            value = self._platform_serial
            self._platform_serial = 1 if value >= 0xFFFF else value + 1
            return value

    @staticmethod
    def _unescape(data):
        output = bytearray()
        index = 0
        while index < len(data):
            value = data[index]
            if value == 0x7D and index + 1 < len(data):
                following = data[index + 1]
                if following == 0x02:
                    output.append(0x7E)
                    index += 2
                    continue
                if following == 0x01:
                    output.append(0x7D)
                    index += 2
                    continue
            output.append(value)
            index += 1
        return bytes(output)

    @staticmethod
    def _escape(data):
        output = bytearray()
        for value in data:
            if value == 0x7E:
                output.extend((0x7D, 0x02))
            elif value == 0x7D:
                output.extend((0x7D, 0x01))
            else:
                output.append(value)
        return bytes(output)
