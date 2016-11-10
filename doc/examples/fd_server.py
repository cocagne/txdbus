#!/usr/bin/env python


from __future__ import print_function

import os

from twisted.internet import reactor, defer

from txdbus import client, objects, interface


class FDObject(objects.DBusObject):

    iface = interface.DBusInterface(
        'org.example.FDInterface',
        interface.Method('lenFD', arguments='h', returns='t'),
    )

    dbusInterfaces = [iface]

    def dbus_lenFD(self, fd):
        print('handling lenFD(fd=%r)' % (fd,), end=' ')
        f = os.fdopen(fd)
        result = len(f.read())
        f.close()
        print('result=%r' % (result,))
        return result
        
    
@defer.inlineCallbacks
def main(reactor):

    PATH = '/path/to/FDObject'
    BUSN = 'org.example'

    bus = yield client.connect(reactor)
    print('connected')
    object = FDObject(PATH)
    bus.exportObject(object)
    yield bus.requestBusName(BUSN)
    print('exported object on %r at %r' % (BUSN, PATH))


if __name__ == '__main__':

    reactor.callWhenRunning(main, reactor)
    reactor.run()

