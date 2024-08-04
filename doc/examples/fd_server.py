#!/usr/bin/env python3

"""
fd_server.py

Publishes FDObject at PATH on BUSN (see code), demonstrating server side
implementation of methods with open UNIX file descriptors as arguments
(type 'h' as per the dbus spec).

NOTE::
Passing open UNIX filedescriptors accross RPC / ICP mechanisms such as dbus
requires the underlying transport to be a UNIX domain socket.
"""



import os

import twisted
from twisted.internet import defer, reactor

from txdbus import client, interface, objects


def trace_method_call(method):

    def wrapper(*args, **kwargs):
        print(f'handling {method.__name__}{args[1:]!r}', end=' = ')
        result = method(*args, **kwargs)
        print(repr(result))
        return result

    return wrapper


class FDObject(objects.DBusObject):

    _methods = [
        'org.example.FDInterface',
        interface.Method('lenFD', arguments='h', returns='t'),
        interface.Method('readBytesFD', arguments='ht', returns='ay'),
    ]

    @trace_method_call
    def dbus_lenFD(self, fd):
        """
        Returns the byte count after reading till EOF.
        """
        f = os.fdopen(fd, 'rb')
        result = len(f.read())
        f.close()
        return result

    @trace_method_call
    def dbus_readBytesFD(self, fd, byte_count):
        """
        Reads byte_count bytes from fd and returns them.
        """
        f = os.fdopen(fd, 'rb')
        result = f.read(byte_count)
        f.close()
        return bytearray(result)

    @trace_method_call
    def dbus_readBytesTwoFDs(self, fd1, fd2, byte_count):
        """
        Reads byte_count from fd1 and fd2. Returns concatenation.
        """
        result = bytearray()
        for fd in (fd1, fd2):
            f = os.fdopen(fd, 'rb')
            result.extend(f.read(byte_count))
            f.close()
        return result

    # Only export 'readBytesTwoFDs' if we're running Twisted >= 17.1.0 which
    # is required to handle multiple UNIX FD arguments.

    _minTxVersion = type(twisted.version)('twisted', 17, 1, 0)
    if twisted.version >= _minTxVersion:
        _methods.append(
            interface.Method('readBytesTwoFDs', arguments='hht', returns='ay')
        )
    else:
        print('Twisted version < {}, not exposing {!r}'.format(
            _minTxVersion.base(),
            'readBytesTwoFDs'
        ))
    del _minTxVersion

    dbusInterfaces = [interface.DBusInterface(*_methods)]


@defer.inlineCallbacks
def main(reactor):

    PATH = '/path/to/FDObject'
    BUSN = 'org.example'

    try:
        bus = yield client.connect(reactor)
    except Exception as e:
        print(f'failed connecting to dbus: {e}')
        reactor.stop()
        defer.returnValue(None)

    print('connected to dbus')
    object = FDObject(PATH)
    bus.exportObject(object)
    yield bus.requestBusName(BUSN)
    print(f'exported {object.__class__.__name__!r} on {BUSN!r} at {PATH!r}')


if __name__ == '__main__':
    reactor.callWhenRunning(main, reactor)
    reactor.run()
