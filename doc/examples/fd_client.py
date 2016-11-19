#!/usr/bin/env python

"""
fd_client.py

Grabs '/path/to/FDObject' on 'org.example' bus and demonstrates calling
remote methods with UNIX open file descriptors as arguments (type 'h' as
per the dbus spec).

NOTE:
Passing open UNIX filedescriptors accross RPC / ICP mechanisms such as dbus
requires the underlying transport to be a UNIX domain socket.
"""

from __future__ import print_function

from twisted.internet import defer, task

from txdbus import client


@defer.inlineCallbacks
def call_remote_verbose(obj, method, *args, **kwargs):

    print('%s%s' % (method, args), end=' = ')
    result = yield obj.callRemote(method, *args, **kwargs)
    print(repr(result))
    defer.returnValue(result)


@defer.inlineCallbacks
def main(reactor):

    PATH = '/path/to/FDObject'
    BUSN = 'org.example'

    bus = yield client.connect(reactor)
    print('connected to dbus')
    object = yield bus.getRemoteObject(BUSN, PATH)
    print('obtained remote object')

    # Open this source file. Ask remote to read it and return byte count.
    with open(__file__, 'rb') as f:
        yield call_remote_verbose(object, 'lenFD', f.fileno())

    # Open this source file. Ask remote to read 10 bytes from it.
    with open(__file__, 'rb') as f:
        yield call_remote_verbose(object, 'readBytesFD', f.fileno(), 10)

    # IMPORTANT
    # ---------
    # The following call is commented because the current implementation
    # fails at handling calls with more than one UNIX FD arument. The client
    # call goes through, but the server side fails at receiving more than one FD.

#    # Like the previous one - exercise passing two open UNIX FDs.
#    with open(__file__, 'rb') as f1, open(__file__, 'rb') as f2:
#        fd1 = f1.fileno()
#        fd2 = f2.fileno()
#        yield call_remote_verbose(object, 'readBytesTwoFDs', fd1, fd2, 5)

    bus.disconnect()


if __name__ == '__main__':

    task.react(main)

