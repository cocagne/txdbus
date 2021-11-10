import binascii
import getpass
import os
import os.path
import shutil
import tempfile
import time

from twisted.internet import defer, interfaces, protocol, reactor
from twisted.internet.protocol import Factory
from twisted.trial import unittest
from zope.interface import implementer

from txdbus import authentication, bus, endpoints
from txdbus.authentication import DBusAuthenticationFailed


class GetPass:
    def getuser(self):
        return 'testuser'


tohex = binascii.hexlify
unhex = binascii.unhexlify


class ClientAuthenticatorTester(unittest.TestCase):

    def setUp(self):
        authentication.getpass = GetPass()  # override 'getpass' module
        self.ca = authentication.ClientAuthenticator()
        self.reply = None

        self.ca.beginAuthentication(self)

    def tearDown(self):
        authentication.getpass = getpass

    def sendAuthMessage(self, m):
        self.reply = m

    def send(self, msg):
        self.ca.handleAuthMessage(msg)

    def ae(self, x, y):
        self.assertEqual(x, y)

    def are(self, x):
        self.assertEqual(self.reply, x)

    def test_bad_auth_message(self):
        self.assertRaises(DBusAuthenticationFailed, self.send, b'BAD_LINE')

    def test_rejection(self):
        self.ae(self.ca.authMech, b'EXTERNAL')
        self.are(b'AUTH EXTERNAL')
        self.send(b'REJECTED')
        self.ae(self.ca.authMech, b'DBUS_COOKIE_SHA1')
        self.are(b'AUTH DBUS_COOKIE_SHA1 ' + tohex(b'testuser'))
        self.send(b'REJECTED')
        self.ae(self.ca.authMech, b'ANONYMOUS')
        self.are(b'AUTH ANONYMOUS 747864627573')
        self.assertRaises(DBusAuthenticationFailed, self.send, b'REJECTED')

    def test_error(self):
        self.ae(self.ca.authMech, b'EXTERNAL')
        self.are(b'AUTH EXTERNAL')
        self.send(b'ERROR')
        self.ae(self.ca.authMech, b'DBUS_COOKIE_SHA1')
        self.are(b'AUTH DBUS_COOKIE_SHA1 ' + tohex(b'testuser'))
        self.send(b'ERROR')
        self.ae(self.ca.authMech, b'ANONYMOUS')
        self.are(b'AUTH ANONYMOUS 747864627573')

    def test_ok(self):
        self.assertRaises(DBusAuthenticationFailed, self.send, b'OK')
        self.assertRaises(DBusAuthenticationFailed, self.send, b'OK foo')
        self.send(b'OK ' + tohex(b'foo'))
        self.ae(self.ca.getGUID(), b'foo')
        self.are(b'BEGIN')
        self.assertTrue(self.ca.authenticationSucceeded())

    def test_unix_fd_disagree(self):
        self.assertRaises(
            DBusAuthenticationFailed,
            self.send,
            b'AGREE_UNIX_FD',
        )

    def test_unix_fd_agree(self):

        @implementer(interfaces.IUNIXTransport)
        class FakeUNIXTransport:
            def write(self, data):
                pass

            def writeSequence(self, data):
                pass

            def loseConnection(self):
                pass

            def getPeer(self):
                pass

            def getHost(self):
                pass

            def sendFileDescriptor(self, descriptor):
                pass

        self.transport = FakeUNIXTransport()

        # "re-"begin authentication after faking my transport
        self.ca.beginAuthentication(self)

        self.send(b'OK ' + tohex(b'foo'))
        self.are(b'NEGOTIATE_UNIX_FD')
        self.send(b'AGREE_UNIX_FD')
        self.are(b'BEGIN')
        del self.transport

    def test_data_external(self):
        self.ca.authMech = b'EXTERNAL'
        self.send(b'DATA')
        self.are(b'DATA')

    def test_get_cookie(self):
        t = tempfile.mkdtemp()
        k = os.path.join(t, 'keyring')
        ctx = b'foo'
        cid = b'bar'
        fn = os.path.join(k, ctx.decode('ascii'))

        try:
            os.mkdir(k, 0o0777)
            self.ca.cookie_dir = k

            self.assertRaises(
                Exception,
                self.ca._authGetDBusCookie,
                None,
                None,
            )
            os.chmod(k, 0o0700)

            self.ca.cookie_dir = '/etc'
            self.assertRaises(
                Exception,
                self.ca._authGetDBusCookie,
                None,
                None,
            )

            with open(fn, 'wb') as f:
                f.write(b'abcd 12345 234234234\n')
                f.write(b'bar  12345 123456\n')

            self.ca.cookie_dir = k
            self.ae(self.ca._authGetDBusCookie(ctx, cid), b'123456')

        finally:
            shutil.rmtree(t)

    def test_data_dbus_cookie_sha1_err(self):
        self.ca.authMech = b'DBUS_COOKIE_SHA1'
        self.send(b'DATA ACK!')
        self.are(b'ERROR Non-hexadecimal digit found')


class BusCookieAuthenticatorTester(unittest.TestCase):

    def setUp(self):
        self.ba = authentication.BusCookieAuthenticator()

    def ae(self, x, y):
        self.assertEqual(x, y)

    def ar(self, x):
        self.assertEqual(x, ('REJECTED', None))

    def s(self, x):
        return self.ba.step(x)

    def s1(self, x, y=None):
        return self.ba._step_one(x, y)

    def s2(self, x):
        return self.ba._step_two(x)

    def test_mech_name(self):
        self.ae(self.ba.getMechanismName(), 'DBUS_COOKIE_SHA1')

    def test_step(self):
        self.ar(self.s(None))
        self.ba.step_num = 2
        self.ar(self.s('foo'))

    def test_step1_invalid_username(self):
        self.ar(self.s1('foobarbazwannabewilliamwallace'))

    def test_step1_invalid_uid(self):
        self.ar(self.s1(99999999999))

    def test_step1_bad_user_keyring_permissions(self):
        t = tempfile.mkdtemp()
        k = os.path.join(t, 'keyring')
        try:
            os.mkdir(k, 0o0777)

            self.ar(self.s1(0, k))
        finally:
            shutil.rmtree(t)

    def test_step1_create_user_keyring_dir(self):
        t = tempfile.mkdtemp()
        k = os.path.join(t, 'keyring')
        try:

            self.assertTrue(not os.path.exists(k))
            self.ae(self.s1(0, k)[0], 'CONTINUE')
            self.assertTrue(os.path.exists(k))

        finally:
            shutil.rmtree(t)

    def test_step2_fail(self):
        t = tempfile.mkdtemp()
        k = os.path.join(t, 'keyring')
        try:

            self.assertTrue(not os.path.exists(k))
            self.ae(self.s1(0, k)[0], 'CONTINUE')
            self.assertTrue(os.path.exists(k))
            self.ar(self.s2('INVALID RESPONSE'))

        finally:
            shutil.rmtree(t)

    def test_lock(self):
        t = tempfile.mkdtemp()
        k = os.path.join(t, 'keyring')
        try:
            self.assertTrue(not os.path.exists(k))
            self.ae(self.s1(0, k)[0], 'CONTINUE')
            self.assertTrue(os.path.exists(k))

            lf = self.ba.cookie_file + '.lock'
            with open(lf, 'w') as f:
                f.write('\0')

            self.ba._get_lock()
            self.assertTrue(True)
        finally:
            shutil.rmtree(t)


class DBusCookieAuthenticationTester(unittest.TestCase):

    def setUp(self):
        authentication.getpass = GetPass()  # override 'getpass' module
        self.ca = authentication.ClientAuthenticator()
        self.ba = authentication.BusCookieAuthenticator()
        self.reply = None

        self.ca.beginAuthentication(self)

    def tearDown(self):
        authentication.getpass = getpass

    def sendAuthMessage(self, m):
        self.reply = m

    def send(self, msg):
        self.ca.handleAuthMessage(msg)

    def test_dbus_cookie_authentication(self):
        self.assertEqual(self.ba.getMechanismName(), 'DBUS_COOKIE_SHA1')

        while not self.ca.authMech == b'DBUS_COOKIE_SHA1':
            self.ca.authTryNextMethod()
        self.assertEqual(
            self.reply,
            b'AUTH DBUS_COOKIE_SHA1 '
            + tohex(b'testuser'),
        )

        t = tempfile.mkdtemp()
        k = os.path.join(t, 'keyring')
        try:
            self.ca.cookie_dir = k
            s1 = self.ba._step_one('0', k)
            self.assertEqual(s1[0], 'CONTINUE')
            self.send(b'DATA ' + tohex(s1[1]))
            self.assertTrue(self.reply.startswith(b'DATA'))
            self.assertEqual(
                self.ba._step_two(unhex(self.reply.split()[1])),
                ('OK', None),
            )
        finally:
            shutil.rmtree(t)


class DBusCookieCookieHandlingTester(unittest.TestCase):

    def setUp(self):
        self.ba = authentication.BusCookieAuthenticator()
        self.t = tempfile.mkdtemp()

        self.ba.cookie_file = os.path.join(self.t, 'nomnomnom')

    def tearDown(self):
        shutil.rmtree(self.t)

    def test_make_cookies(self):
        def g(t):
            def tf():
                return time.time() - t
            return tf
        self.ba._create_cookie(g(31.0))
        self.ba._create_cookie(g(31.0))
        self.ba._create_cookie(g(20.0))
        self.ba._create_cookie(g(21.2))
        c = self.ba._get_cookies()
        self.assertEqual({b'3', b'4'}, {x[0] for x in c})

    def test_del_cookie_with_remaining(self):
        self.ba._create_cookie()
        self.ba._create_cookie()
        self.ba._create_cookie()
        self.ba.cookieId = 2
        self.ba._delete_cookie()
        c = self.ba._get_cookies()
        self.assertEqual({b'1', b'3'}, {x[0] for x in c})

    def test_del_cookie_last(self):
        self.ba._create_cookie()
        self.ba.cookieId = 1
        self.assertTrue(os.path.exists(self.ba.cookie_file))
        self.ba._delete_cookie()
        self.assertTrue(not os.path.exists(self.ba.cookie_file))


class ExternalAuthMechanismTester(unittest.TestCase):

    def test_external_auth_logic(self):
        bea = authentication.BusExternalAuthenticator()

        self.assertEqual(bea.getMechanismName(), 'EXTERNAL')

        class T:
            _unix_creds = None

        bea.init(T())

        self.assertEqual(
            bea.step(''),
            ('REJECT', 'Unix credentials not available'),
        )

        bea.creds = ('foo', 0)

        self.assertEqual(bea.step(''), ('CONTINUE', ''))
        self.assertEqual(bea.step(''), ('OK', None))

        self.assertEqual(bea.getUserName(), 'root')

        bea.cancel()


class AnonymousAuthMechanismTester(unittest.TestCase):

    def test_anonymous_auth_logic(self):
        baa = authentication.BusAnonymousAuthenticator()

        self.assertEqual(baa.getMechanismName(), 'ANONYMOUS')

        baa.init(None)

        self.assertEqual(baa.step(''), ('OK', None))

        self.assertEqual(baa.getUserName(), 'anonymous')

        baa.cancel()


# ---------------------------------------------------------------------
# Protocol Level Tests
# ---------------------------------------------------------------------


# Always use the internal bus for tests if a system bus isn't available
# typically the session bus won't exist on Windows
#
INTERNAL_BUS = 'DBUS_SESSION_BUS_ADDRESS' not in os.environ

INTERNAL_BUS = True


def delay(arg):
    d = defer.Deferred()
    reactor.callLater(0.05, lambda: d.callback(arg))
    return d


def get_username():
    uname = os.environ.get('USERNAME', None)

    if uname is None:
        uname = os.environ.get('LOGNAME', None)

    return uname.encode('ascii')


class AuthTestProtocol(protocol.Protocol):
    _buffer = b''
    _sent_null = False

    def connectionMade(self):
        self.disconnect_d = None
        self.disconnect_timeout = None
        self.fail_exit_d = None

        self.factory._ok(self)

    def dataReceived(self, data):
        lines = (self._buffer + data).split(b'\r\n')
        self._buffer = lines.pop(-1)

        for line in lines:
            self.gotMessage(line)

    def disconnect(self):
        self.transport.loseConnection()

    def setTest(self, test):
        self.test = test
        self.assertTrue = self.test.assertTrue
        self.assertEquals = self.test.assertEquals
        self.fail = self.test.fail

    def succeed(self):
        self.assertTrue(True)

    def connectionLost(self, reason):
        if self.disconnect_d:

            if self.disconnect_timeout:
                self.disconnect_timeout.cancel()
                self.disconnect_timeout = None

            d = self.disconnect_d
            self.disconnect_d = None
            d.callback(None)

        elif self.fail_exit_d:
            d = self.fail_exit_d
            self.fail_exit_d = None

            d.errback(unittest.FailTest('Connection unexpectedly dropped'))

    def failOnExit(self):
        self.fail_exit_d = defer.Deferred()

        def cleanup(_):
            self.fail_exit_d = None
            return _
        self.fail_exit_d.addCallback(cleanup)
        return self.fail_exit_d

    def expectDisconnect(self):
        self.disconnect_d = defer.Deferred()

        def timeout():
            self.fail()
            d = self.disconnect_d
            self.disconnect_d = None
            d.errback(Exception('Disconnect timed out'))

        self.disconnect_timeout = reactor.callLater(2, timeout)

        self.disconnect_d.addCallback(lambda _: self.succeed())

        return self.disconnect_d

    def send(self, msg):
        if not self._sent_null:
            self.transport.write(b'\0')
            self._sent_null = True
        self.transport.write(msg + b'\r\n')

    def test_no_null_byte_at_start(self):
        d = self.expectDisconnect()
        self.transport.write(b'blah')
        return d

    def test_bad_command(self):
        d = self.failOnExit()
        self.send(b'FISHY')

        def recv(msg):
            self.assertEqual(msg, b'ERROR "Unknown command"')
            d.callback(None)
        self.gotMessage = recv
        return d

    def test_bad_mech(self):
        d = self.failOnExit()
        self.send(b'AUTH FOOBAR')

        def recv(msg):
            self.assertTrue(msg.startswith(b'REJECTED'))
            d.callback(None)
        self.gotMessage = recv
        return d

    def test_bad_mech2(self):
        d = self.failOnExit()
        self.send(b'AUTH FOO BAR')

        def recv(msg):
            self.assertTrue(msg.startswith(b'REJECTED'))
            d.callback(None)
        self.gotMessage = recv
        return d

    def test_too_long(self):
        d = self.expectDisconnect()
        self.send(b'AUTH ' + b'A' * 17000)
        return d

    def test_max_rejects(self):
        d = self.expectDisconnect()

        def retry(_=None):
            dr = defer.Deferred()
            self.send(b'AUTH FOOBAR')

            def recv(msg):
                self.assertTrue(msg.startswith(b'REJECTED'))
                dr.callback(None)
            self.gotMessage = recv
            return dr

        x = retry()
        x.addCallback(retry)
        x.addCallback(retry)
        x.addCallback(retry)
        x.addCallback(retry)
        x.addCallback(retry)

        return d

    def test_reject(self):
        d = self.failOnExit()
        self.send(b'AUTH DBUS_COOKIE_SHA1')

        def recv(msg):
            self.assertTrue(msg.startswith(b'REJECTED'))
            d.callback(None)
        self.gotMessage = recv
        return d

    def test_retry(self):
        d = self.failOnExit()
        self.send(b'AUTH DBUS_COOKIE_SHA1')

        def recv2(msg):
            self.assertTrue(msg.startswith(b'DATA'))
            d.callback(None)

        def recv1(msg):
            self.send(
                b'AUTH DBUS_COOKIE_SHA1 '
                + binascii.hexlify(
                    get_username()))
            self.assertTrue(msg.startswith(b'REJECTED'))
            self.gotMessage = recv2

        self.gotMessage = recv1
        return d

    def test_cancel(self):
        d = self.failOnExit()

        self.send(b'AUTH DBUS_COOKIE_SHA1 ' + binascii.hexlify(get_username()))

        def recv2(msg):
            self.assertTrue(msg.startswith(b'REJECTED'))
            d.callback(None)

        def recv1(msg):
            self.send(b'CANCEL')
            self.assertTrue(msg.startswith(b'DATA'))
            self.gotMessage = recv2

        self.gotMessage = recv1
        return d


class AuthFactory (Factory):
    """
    Factory for DBusClientConnection instances
    """
    protocol = AuthTestProtocol

    def __init__(self):
        self.d = defer.Deferred()

    def _ok(self, proto):
        self.d.callback(proto)

    def _failed(self, err):
        self.d.errback(err)

    def getConnection(self):
        """
        Returns the fully-connected DBusClientConnection instance. This method
        should be used to obtain a reference to the DBusClientConnection as it
        will be called back/error backed after authentication and DBus session
        registration are complete.
        """
        return self.d


class ServerObjectTester(unittest.TestCase):

    def setUp(self):

        if INTERNAL_BUS:
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
                return self._client_connect()

            d.addCallback(got_port)

            return d
        else:
            return self._client_connect()

    def _client_connect(self):
        self.conn = None

        f = AuthFactory()

        point = endpoints.getDBusEnvEndpoints(reactor)[0]
        point.connect(f)

        d = f.getConnection()
        d.addCallback(self._connected)

        return d

    def _connected(self, conn):
        self.conn = conn
        self.conn.setTest(self)

    def tearDown(self):

        if self.conn:
            self.conn.disconnect()

        if INTERNAL_BUS:
            return self.port.stopListening()

    def test_no_null_byte_at_start(self):
        return self.conn.test_no_null_byte_at_start()

    def test_bad_command(self):
        return self.conn.test_bad_command()

    def test_bad_mech(self):
        return self.conn.test_bad_mech()

    def test_bad_mech2(self):
        return self.conn.test_bad_mech2()

    def test_too_long(self):
        return self.conn.test_too_long()

    def test_reject(self):
        return self.conn.test_reject()

    def test_retry(self):
        return self.conn.test_retry()

    def test_cancel(self):
        return self.conn.test_cancel()

    def test_max_rejects(self):
        return self.conn.test_max_rejects()
