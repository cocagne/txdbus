#!/usr/bin/env python


from __future__ import print_function

from twisted.internet import defer, task

from txdbus import client


@defer.inlineCallbacks
def main(reactor):

    bus = yield client.connect(reactor)
    print('connected')
    object = yield bus.getRemoteObject('org.example', '/path/to/FDObject')
    print('obtained remote object')

    with open(__file__, 'rt') as f:
        fd = f.fileno()
        print('calling lenFD(%i) -' % (fd,), end=' ')
        result = yield object.callRemote('lenFD', f.fileno())
        print('result=%r' % (result,))


if __name__ == '__main__':

    task.react(main)

