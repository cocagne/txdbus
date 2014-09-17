import os
from twisted.trial import unittest
from twisted.internet import reactor

from twisted.internet.endpoints import UNIXClientEndpoint, TCP4ClientEndpoint
from twisted.internet.endpoints import UNIXServerEndpoint, TCP4ServerEndpoint

from txdbus import error, endpoints

class EndpointsTester(unittest.TestCase):

    def setUp(self):
        self.pre_ses = os.environ['DBUS_SESSION_BUS_ADDRESS']

    def tearDown(self):
        os.environ['DBUS_SESSION_BUS_ADDRESS'] = self.pre_ses

    def env(self, val):
        if val:
            os.environ['DBUS_SESSION_BUS_ADDRESS'] = val
        else:
            if 'DBUS_SESSION_BUS_ADDRESS' in os.environ:
                del os.environ['DBUS_SESSION_BUS_ADDRESS']

    def gde(self, addr, client=True):
        return endpoints.getDBusEndpoints(reactor, addr, client)
        
    def test_no_session(self):
        self.env(None)
        try:
            endpoints.getDBusEnvEndpoints(reactor)
            self.assertTrue(False)
        except Exception as e:
            self.assertEquals(str(e), 'DBus Session environment variable not set')

    def xtest_env_session(self):
        pass

    def test_unix_address(self):
        e = self.gde('unix:path=/var/run/dbus/system_bus_socket')[0]
        self.assertEquals(e._path, '/var/run/dbus/system_bus_socket')
        e = self.gde('unix:tmpdir=/tmp')[0]
        self.assertTrue(e._path.startswith('/tmp/dbus-'))
        e = self.gde('unix:abstract=/tmp/dbus-jgAbdgyUH7,guid=6abbe624c672777bd87ab46e00027706')[0]
        self.assertEquals(e._path, '\0/tmp/dbus-jgAbdgyUH7')
        e = self.gde('unix:abstract=/tmp/dbus-jgAbdgyUH7', False)[0]
        self.assertEquals(e._address, '\0/tmp/dbus-jgAbdgyUH7')
        self.assertTrue(isinstance(e,UNIXServerEndpoint))

    def test_tcp_address(self):
        e = self.gde('tcp:host=127.0.0.1,port=1234')[0]
        self.assertEquals(e._host, '127.0.0.1')
        self.assertEquals(e._port, 1234)

        e = self.gde('tcp:host=127.0.0.1,port=1234', False)[0]
        self.assertEquals(e._interface, '127.0.0.1')
        self.assertEquals(e._port, 1234)

    def test_nonce_tcp_address(self):
        e = self.gde('nonce-tcp:host=127.0.0.1,port=1234,noncefile=/foo')[0]
        self.assertEquals(e._host, '127.0.0.1')
        self.assertEquals(e._port, 1234)
        self.assertTrue('noncefile' in e.dbus_args)
        self.assertEquals(e.dbus_args['noncefile'], '/foo')

    def test_launchd_address(self):
        l = self.gde('launchd:env=foo')
        self.assertEquals(l,[])
        
    def test_session(self):
        self.env('unix:abstract=/tmp/dbus-jgAbdgyUH7,guid=6abbe624c672777bd87ab46e00027706')
        e = self.gde('session')[0]
        self.assertEquals(e._path, '\0/tmp/dbus-jgAbdgyUH7')

        self.env(None)
        self.assertRaises(Exception, self.gde, 'session')

    def test_system(self):
        e = self.gde('system')[0]
        self.assertEquals(e._path, '/var/run/dbus/system_bus_socket')

    def test_multiple_addresses(self):
        self.env('unix:abstract=/tmp/dbus-jgAbdgyUH7,guid=6abbe624c672777bd87ab46e00027706;tcp:host=127.0.0.1,port=1234')
        l = self.gde('session')
        self.assertTrue(len(l) == 2)
        e = l[0]
        self.assertEquals(e._path, '\0/tmp/dbus-jgAbdgyUH7')
        e = l[1]
        self.assertEquals(e._host, '127.0.0.1')
        self.assertEquals(e._port, 1234)
