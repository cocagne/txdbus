txdbus
======

Tom Cocagne <tom.cocagne@gmail.com>
v1.0, July 2012

Introduction
------------

TxDBus is a native Python implementation of the
[DBus protocol](http://dbus.freedesktop.org/doc/dbus-specification.html)
for the [Twisted](http://twistedmatrix.com/trac/) networking framework.

In addition to a [Tutorial](http://packages.python.org/txdbus), and collection
of [Examples](https://github.com/cocagne/txdbus/tree/master/doc/tutorial_examples),
the documentation for this project also includes
[An Overview of the DBus Protocol](http://packages.python.org/txdbus/dbus_overview.html)

*License*: [MIT](http://www.opensource.org/licenses/mit-license.php)

Usage Example
-------------

```python
#!/usr/bin/python

from twisted.internet import reactor, defer
from txdbus import error, client

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
```

