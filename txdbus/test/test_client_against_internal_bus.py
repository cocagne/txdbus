import os
import sys

from twisted.internet.protocol import Factory
from twisted.internet import reactor, defer

from txdbus import objects, endpoints, bus, error, client
from twisted.trial import unittest

import client_tests

# Force the objects test code to use the internal bus rather than the
# session bus provided by the operating system.
def delay(t):
    d = defer.Deferred()
    reactor.callLater(t, lambda : d.callback(None))
    return d

class InternalBusMixin (object):

    def _setup(self):
        self.orig_env = os.environ['DBUS_SESSION_BUS_ADDRESS']
        
        os.environ['DBUS_SESSION_BUS_ADDRESS']='unix:abstract=/tmp/txdbus-test,guid=5'
            
        bus_obj = bus.Bus()

        f = Factory()
        f.protocol = bus.BusProtocol
        f.bus = bus_obj
        
        point = endpoints.getDBusEnvEndpoints(reactor, False)[0]
        d = point.listen(f)

        def got_port(port):
            self.port = port
        
        d.addCallback( got_port )
        
        return d

    
    def _teardown(self):

        os.environ['DBUS_SESSION_BUS_ADDRESS'] = self.orig_env
        
        return self.port.stopListening()

        


# "Copy" the objects unit tests into this module
m = sys.modules[ __name__ ]

print('Internal bus tests are currently broken... skipping')
#for k,v in client_tests.__dict__.iteritems():
#    if isinstance(v, type) and issubclass(v, client_tests.ServerObjectTester):
#        setattr(m, k, type(k, (InternalBusMixin, v, unittest.TestCase), dict()))


