# Copyright (C) 2011 by jedi95 <jedi95@gmail.com> and
#                       CFSworks <CFSworks@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import struct

# Some SHA-256 constants...
K = [
     0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
     0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
     0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
     0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
     0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
     0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
     0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
     0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
     0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
     0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
     0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ]

A0 = 0x6a09e667
B0 = 0xbb67ae85
C0 = 0x3c6ef372
D0 = 0xa54ff53a
E0 = 0x510e527f
F0 = 0x9b05688c
G0 = 0x1f83d9ab
H0 = 0x5be0cd19

def rotateright(i,p):
    """i>>>p"""
    p &= 0x1F # p mod 32
    return i>>p | ((i<<(32-p)) & 0xFFFFFFFF)

def addu32(*i):
    return sum(list(i))&0xFFFFFFFF

def calculateMidstate(data, state=None, rounds=None):
    """Given a 512-bit (64-byte) block of (little-endian byteswapped) data,
    calculate a Bitcoin-style midstate. (That is, if SHA-256 were little-endian
    and only hashed the first block of input.)
    """
    if len(data) != 64:
        raise ValueError('data must be 64 bytes long')

    w = list(struct.unpack('<IIIIIIIIIIIIIIII', data))

    if state is not None:
        if len(state) != 32:
            raise ValueError('state must be 32 bytes long')
        a,b,c,d,e,f,g,h = struct.unpack('<IIIIIIII', state)
    else:
        a = A0
        b = B0
        c = C0
        d = D0
        e = E0
        f = F0
        g = G0
        h = H0

    consts = K if rounds is None else K[:rounds]
    for k in consts:
        s0 = rotateright(a,2) ^ rotateright(a,13) ^ rotateright(a,22)
        s1 = rotateright(e,6) ^ rotateright(e,11) ^ rotateright(e,25)
        ma = (a&b) ^ (a&c) ^ (b&c)
        ch = (e&f) ^ ((~e)&g)

        h = addu32(h,w[0],k,ch,s1)
        d = addu32(d,h)
        h = addu32(h,ma,s0)

        a,b,c,d,e,f,g,h = h,a,b,c,d,e,f,g

        s0 = rotateright(w[1],7) ^ rotateright(w[1],18) ^ (w[1] >> 3)
        s1 = rotateright(w[14],17) ^ rotateright(w[14],19) ^ (w[14] >> 10)
        w.append(addu32(w[0], s0, w[9], s1))
        w.pop(0)

    if rounds is None:
        a = addu32(a, A0)
        b = addu32(b, B0)
        c = addu32(c, C0)
        d = addu32(d, D0)
        e = addu32(e, E0)
        f = addu32(f, F0)
        g = addu32(g, G0)
        h = addu32(h, H0)

    return struct.pack('<IIIIIIII', a, b, c, d, e, f, g, h)