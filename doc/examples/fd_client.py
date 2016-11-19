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

    # IMPORTANT
    # ---------
    # The following calls are commented out for two reasons:
    # - Current implementation seems to fail calling a remote method with
    #   UNIX FDs as arguments more than once. In other words, calling the
    #   above coded 'lenFD' twice, for example, fails on the second attempt.
    #   DBus seems to be closing the connection when getting the 2nd call.
    #   (so, if you want to test the next example call of 'readBytesFD',
    #   for now you will need to comment out the previous call of 'lenFD')
    # - Additionally, the current implementation fails at handling calls
    #   with more than one UNIX FD arument. Failure behavior is different,
    #   though: the client call goes through, but the server side does not
    #   seem to handle receiving more than one FD.

#    # Open this source file. Ask remote to read 10 bytes from it.
#    with open(__file__, 'rb') as f:
#        yield call_remote_verbose(object, 'readBytesFD', f.fileno(), 10)

#    # Like the previous one - exercise passing two open UNIX FDs.
#    with open(__file__, 'rb') as f1, open(__file__, 'rb') as f2:
#        fd1 = f1.fileno()
#        fd2 = f2.fileno()
#        yield call_remote_verbose(object, 'readBytesTwoFDs', fd1, fd2, 5)

    bus.disconnect()


if __name__ == '__main__':

    task.react(main)

