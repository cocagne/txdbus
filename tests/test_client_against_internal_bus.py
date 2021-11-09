import os
import sys
from unittest import SkipTest

import six
from twisted.internet import defer, reactor
from twisted.internet.protocol import Factory
from twisted.trial import unittest

from tests import client_tests
from txdbus import bus, endpoints

# Force the objects test code to use the internal bus rather than the
# session bus provided by the operating system.


def delay(t):
    d = defer.Deferred()
    reactor.callLater(t, lambda: d.callback(None))
    return d


class InternalBusMixin :

    def _setup(self):
        raise SkipTest('Internal bus tests are currently broken.')

        self.orig_env = os.environ['DBUS_SESSION_BUS_ADDRESS']
        os.environ['DBUS_SESSION_BUS_ADDRESS'] = (
            'unix:abstract=/tmp/txdbus-test,guid=5'
        )

        bus_obj = bus.Bus()

        f = Factory()
        f.protocol = bus.BusProtocol
        f.bus = bus_obj

        point = endpoints.getDBusEnvEndpoints(reactor, False)[0]
        d = point.listen(f)

        def got_port(port):
            self.port = port

        d.addCallback(got_port)

        return d

    def _teardown(self):
        os.environ['DBUS_SESSION_BUS_ADDRESS'] = self.orig_env
        return self.port.stopListening()


# "Copy" the objects unit tests into this module
m = sys.modules[__name__]

for k, v in client_tests.__dict__.items():
    if (
        isinstance(v, type) and issubclass(v, client_tests.ServerObjectTester)
    ):
        setattr(m, k, type(k, (InternalBusMixin, v, unittest.TestCase), {}))
