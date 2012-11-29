# Original source: https://gitorious.org/midstate/midstate

import struct
import binascii
from midstate import SHA256

test_data = binascii.unhexlify("0000000293d5a732e749dbb3ea84318bd0219240a2e2945046015880000003f5000000008d8e2673e5a071a2c83c86e28033b1a0a4aac90dde7a0670827cd0c3ef8caf7d5076c7b91a057e0800000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000")
test_target_midstate = binascii.unhexlify("4c8226f95a31c9619f5197809270e4fa0a2d34c10215cf4456325e1237cb009d")


def midstate(data):
    reversed = struct.pack('>IIIIIIIIIIIIIIII', *struct.unpack('>IIIIIIIIIIIIIIII', data[:64])[::-1])[::-1]
    return struct.pack('<IIIIIIII', *SHA256(reversed))

def test():
    return midstate(test_data) == test_target_midstate

if __name__ == '__main__':
    print "target:  ", binascii.hexlify(test_target_midstate)
    print "computed:", binascii.hexlify(midstate(test_data))
    print "passed:  ", test()
