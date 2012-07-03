#!/usr/bin/env python

from twisted.internet import reactor, defer
from tx.dbus import error, client

@defer.inlineCallbacks
def show_desktop_notification():
    '''
    Displays "Hello World!" in a desktop notification window for 3 seconds
    '''
    con = yield client.connect(reactor, 'session')

    notifier = yield con.getRemoteObject('org.freedesktop.Notifications',
                                         '/org/freedesktop/Notifications')

    nid = yield notifier.callRemote('Notify',
                                    'Example Application', 
                                    0,
                                    '',
                                    'Tx DBus Example',
                                    'Hello World!',
                                    [], dict(),
                                    10)
    
    d = defer.Deferred()
    reactor.callLater(3, lambda : d.callback(None))
    yield d

    yield notifier.callRemote('CloseNotification', nid)

    reactor.stop()

reactor.callWhenRunning(show_desktop_notification)
reactor.run()





