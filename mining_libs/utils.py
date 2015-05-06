import hashlib
import struct

from twisted.internet import defer, reactor
from twisted.web import client

import stratum.logger
log = stratum.logger.get_logger('proxy')

def show_message(msg):
    '''Repeatedly displays the message received from
    the server.'''
    log.warning("MESSAGE FROM THE SERVER OPERATOR: %s" % msg)
    log.warning("Restart proxy to discard the message")
    reactor.callLater(10, show_message, msg)

def format_hash(h):
    # For printing hashes to console
    return "%s" % h[:8]
  
def uint256_from_str(s):
    r = 0L
    t = struct.unpack("<IIIIIIII", s[:32])
    for i in xrange(8):
        r += t[i] << (i * 32)
    return r

def uint256_to_str(u):
    rs = ""
    for i in xrange(8):
        rs += struct.pack("<I", u & 0xFFFFFFFFL)
        u >>= 32
    return rs  

def reverse_hash(h):
    return struct.pack('>IIIIIIII', *struct.unpack('>IIIIIIII', h)[::-1])[::-1]
     
def doublesha(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()

@defer.inlineCallbacks
def detect_stratum(host, port):
    '''Perform getwork request to given
    host/port. If server respond, it will
    try to parse X-Stratum header.
    Not the most elegant code, but it works,
    because Stratum server should close the connection
    when client uses unknown payload.'''
        
    def get_raw_page(url, *args, **kwargs):
        # In Twisted 13.1.0 _parse() function replaced by _URI class.
        # In Twisted 15.0.0 _URI class renamed to URI.
        if hasattr(client, "_parse"):
            scheme, host, port, path = client._parse(url)
        else:
            try:
                from twisted.web.client import _URI as URI
            except ImportError:
                from twisted.web.client import URI

            uri = URI.fromBytes(url)
            scheme = uri.scheme
            host = uri.host
            port = uri.port

        factory = client.HTTPClientFactory(url, *args, **kwargs)
        reactor.connectTCP(host, port, factory)
        return factory

    def _on_callback(_, d):d.callback(True)
    def _on_errback(_, d): d.callback(True)
    f = get_raw_page('http://%s:%d' % (host, port))
    
    d = defer.Deferred()
    f.deferred.addCallback(_on_callback, d)
    f.deferred.addErrback(_on_errback, d)
    (yield d)
    
    if not f.response_headers:
        # Most likely we're already connecting to Stratum
        defer.returnValue((host, port))
    
    header = f.response_headers.get('x-stratum', None)[0]
    if not header:
        # Looks like pool doesn't support stratum
        defer.returnValue(None) 
    
    if 'stratum+tcp://' not in header:
        # Invalid header or unsupported transport
        defer.returnValue(None)
    
    header = header.replace('stratum+tcp://', '').strip()
    host = header.split(':')    
    
    if len(host) == 1:
        # Port is not specified
        defer.returnValue((host[0], 3333))
    elif len(host) == 2:
        defer.returnValue((host[0], int(host[1])))
    
    defer.returnValue(None)