"""
This module implements DBus authentication mechanisms

@author: Tom Cocagne
"""

import binascii
import getpass
import hashlib
import os
import os.path
import time

import six
from twisted.internet import interfaces
from twisted.python import log
from zope.interface import implementer, Interface

from txdbus.error import DBusAuthenticationFailed
from txdbus.protocol import IDBusAuthenticator


@implementer(IDBusAuthenticator)
class ClientAuthenticator (object):
    """
    Implements the client-side portion of the DBus authentication protocol.

    @ivar preference: List of authentication mechanisms to try in the preferred
        order
    @type preference: List of C{string}
    """

    preference = [b'EXTERNAL', b'DBUS_COOKIE_SHA1', b'ANONYMOUS']

    def beginAuthentication(self, protocol):
        self.authenticated = False
        self.protocol = protocol
        self.unixFDSupport = self._usesUnixSocketTransport(self.protocol)
        self.guid = None
        self.cookiedir = None  # used for testing only

        self.authOrder = self.preference[:]
        self.authOrder.reverse()

        self.authTryNextMethod()

    def _usesUnixSocketTransport(self, protocol):

        return (
            getattr(protocol, 'transport', None) and
            interfaces.IUNIXTransport.providedBy(protocol.transport)
        )

    def handleAuthMessage(self, line):
        if b' ' not in line:
            cmd = line
            args = b''
        else:
            cmd, args = line.split(b' ', 1)
        m = getattr(self, '_auth_' + cmd.decode(), None)
        if m:
            m(args)
        else:
            raise DBusAuthenticationFailed(
                'Invalid DBus authentication protocol message: ' +
                line.decode("ascii", "replace")
            )

    def authenticationSucceeded(self):
        return self.authenticated

    def getGUID(self):
        return self.guid

    # -------------------------------------------------

    def sendAuthMessage(self, msg):
        self.protocol.sendAuthMessage(msg)

    def authTryNextMethod(self):
        """
        Tries the next authentication method or raises a failure if all
        mechanisms have been tried.
        """
        if not self.authOrder:
            raise DBusAuthenticationFailed()

        self.authMech = self.authOrder.pop()

        if self.authMech == b'DBUS_COOKIE_SHA1':
            self.sendAuthMessage(
                b'AUTH ' +
                self.authMech +
                b' ' +
                binascii.hexlify(getpass.getuser().encode('ascii'))
            )
        elif self.authMech == b'ANONYMOUS':
            self.sendAuthMessage(
                b'AUTH ' +
                self.authMech +
                b' ' +
                binascii.hexlify(b'txdbus')
            )
        else:
            self.sendAuthMessage(b'AUTH ' + self.authMech)

    def _auth_REJECTED(self, line):
        self.authTryNextMethod()

    def _auth_OK(self, line):
        line = line.strip()

        if not line:
            raise DBusAuthenticationFailed('Missing guid in OK message')

        try:
            self.guid = binascii.unhexlify(line)
        except BaseException:
            raise DBusAuthenticationFailed('Invalid guid in OK message')
        else:
            if self.unixFDSupport:
                self.sendAuthMessage(b'NEGOTIATE_UNIX_FD')
            else:
                self.sendAuthMessage(b'BEGIN')
                self.authenticated = True

    def _auth_AGREE_UNIX_FD(self, line):
        if self.unixFDSupport:
            self.sendAuthMessage(b'BEGIN')
            self.authenticated = True
        else:
            raise DBusAuthenticationFailed(
                'AGREE_UNIX_FD with no NEGOTIATE_UNIX_FD',
            )

    def _auth_DATA(self, line):

        if self.authMech == b'EXTERNAL':
            self.sendAuthMessage(b'DATA')

        elif self.authMech == b'DBUS_COOKIE_SHA1':
            try:
                data = binascii.unhexlify(line.strip())

                cookie_context, cookie_id, server_challenge = data.split()

                server_cookie = self._authGetDBusCookie(
                    cookie_context,
                    cookie_id,
                )

                client_challenge = binascii.hexlify(
                    hashlib.sha1(os.urandom(8)).digest()
                )

                response = b':'.join([
                    server_challenge,
                    client_challenge,
                    server_cookie
                ])

                response = binascii.hexlify(hashlib.sha1(response).digest())

                reply = client_challenge + b' ' + response

                self.sendAuthMessage(b'DATA ' + binascii.hexlify(reply))
            except Exception as e:
                log.msg('DBUS Cookie authentication failed: ' + str(e))
                self.sendAuthMessage(
                    b'ERROR ' + str(e).encode('unicode-escape'))

    def _auth_ERROR(self, line):
        log.msg(
            'Authentication mechanism failed: ' +
            line.decode("ascii", "replace")
        )
        self.authTryNextMethod()

    # -------------------------------------------------

    def _authGetDBusCookie(self, cookie_context, cookie_id):
        """
        Reads the requested cookie_id from the cookie_context file
        """
        # XXX   Ensure we obtain the correct directory for the
        #       authenticating user and that that user actually
        #       owns the keyrings directory

        if self.cookie_dir is None:
            cookie_dir = os.path.expanduser('~/.dbus-keyrings')
        else:
            cookie_dir = self.cookie_dir

        dstat = os.stat(cookie_dir)

        if dstat.st_mode & 0o066:
            raise Exception(
                'User keyrings directory is writeable by other users. '
                'Aborting authentication',
            )

        import pwd
        if dstat.st_uid != pwd.getpwuid(os.geteuid()).pw_uid:
            raise Exception(
                'Keyrings directory is not owned by the current user. '
                'Aborting authentication!',
            )

        path = os.path.join(cookie_dir, cookie_context.decode('ascii'))
        with open(path, 'rb') as f:
            for line in f:
                try:
                    k_id, k_time, k_cookie_hex = line.split()
                    if k_id == cookie_id:
                        return k_cookie_hex
                except BaseException:
                    pass


class IBusAuthenticationMechanism (Interface):
    """
    Classes implementing this interface may be used by Bus instances to
    authenticate users
    """

    def getMechanismName(self):
        """
        @returns: The name of the authentication mechanism
        """

    def init(self, protocol):
        """
        Called to allow authentication mechanism to query protocol state
        """

    def step(self, arg):
        """
        @returns: ('OK' | 'CONTINUE' | 'REJECT', challenge | None)
        """

    def getUserName(self):
        """
        @returns: the name of the user
        """

    def cancel(self):
        """
        Informs the authentication mechanism that the current authentication
        has been canceled and that cleanup is in order
        """


@implementer(IBusAuthenticationMechanism)
class BusCookieAuthenticator (object):
    """
    Implements the Bus-side portion of the DBUS_COOKIE_SHA1 authentication
    mechanism
    """

    cookieContext = 'org_twisteddbus_ctx' + str(os.getpid())

    def __init__(self):
        self.step_num = 0
        self.username = None
        self.cookieId = None

    def cancel(self):
        if self.cookieId:
            self._delete_cookie()

    def getMechanismName(self):
        return 'DBUS_COOKIE_SHA1'

    def init(self, protocol):
        pass

    def getUserName(self):
        return self.username

    def step(self, arg):
        s = self.step_num
        self.step_num += 1

        if arg is None:
            return ('REJECTED', None)

        try:
            if s == 0:
                return self._step_one(arg)
            elif s == 1:
                return self._step_two(arg)
            else:
                raise Exception()
        except Exception as e:
            return ('REJECTED', None)

    def _step_one(self, username, keyring_dir=None):
        try:
            uid = int(username)
            try:
                import pwd
                username = pwd.getpwuid(uid).pw_name
            except BaseException:
                return ('REJECTED', None)
        except ValueError:
            pass

        self.username = username

        try:
            import pwd
            p = pwd.getpwnam(username)
            self.uid = p.pw_uid
            self.gid = p.pw_gid
            self.homedir = p.pw_dir
        except (KeyError, ImportError):
            return ('REJECTED', None)  # username not found

        if keyring_dir is None:
            dk = os.path.join(self.homedir, '.dbus-keyrings')
        else:
            dk = keyring_dir  # for testing only

        self.cookie_file = os.path.join(dk, self.cookieContext)

        try:
            s = os.lstat(dk)
            if not os.path.isdir(dk) or s.st_mode & 0o0066:
                # Invalid keyrings directory. Something fishy is going on
                return ('REJECTED', None)
        except OSError:
            old_un = os.umask(0o0077)
            os.mkdir(dk)
            os.umask(old_un)
            if os.geteuid() == 0:
                os.chown(dk, self.uid, self.gid)

        self._create_cookie()

        self.challenge_str = binascii.hexlify(hashlib.sha1(
                                              os.urandom(8)).digest())

        msg = b' '.join([self.cookieContext.encode('ascii'),
                         str(self.cookieId).encode('ascii'),
                         self.challenge_str])

        return ('CONTINUE', msg)

    def _step_two(self, response):
        self._delete_cookie()
        hash_str = None
        shash = 1
        try:
            client_challenge, hash_str = response.split()

            tohash = (
                self.challenge_str +
                b':' +
                client_challenge +
                b':' +
                self.cookie
            )

            shash = binascii.hexlify(hashlib.sha1(tohash).digest())
        except BaseException:
            pass

        if shash == hash_str:
            return ('OK', None)
        else:
            return ('REJECTED', None)

    def _get_lock(self):
        #
        # Twisted is single-threaded, our context name includes the
        # process id, and we wont be using any deferreds here... so
        # the lock file really isn't needed. We'll go ahead and
        # include a very simple version of it, however, "just to say
        # we did"
        #
        self.lock_file = self.cookie_file + '.lock'
        try:
            lockfd = os.open(
                self.lock_file,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o0600,
            )
        except BaseException:
            time.sleep(0.01)
            try:
                lockfd = os.open(
                    self.lock_file,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o0600,
                )
            except BaseException:
                os.unlink(self.lock_file)
                lockfd = os.open(
                    self.lock_file,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o0600,
                )

        return lockfd

    def _get_cookies(self, timefunc=time.time):
        cookies = []
        try:
            with open(self.cookie_file, 'rb') as f:
                for line in f:
                    k_id, k_time, k_cookie_hex = line.split()

                    if abs(timefunc() - int(k_time)) < 30:
                        cookies.append(line.split())
        except BaseException:
            pass

        return cookies

    def _create_cookie(self, timefunc=time.time):

        lockfd = self._get_lock()

        cookies = self._get_cookies(timefunc)

        cookie_id = 1
        for tpl in cookies:
            if int(tpl[0]) >= cookie_id:
                cookie_id = int(tpl[0]) + 1

        cookie = binascii.hexlify(os.urandom(24))

        cookies.append((
            str(cookie_id).encode('ascii'),
            str(int(timefunc())).encode('ascii'),
            cookie,
        ))

        for c in cookies:
            os.write(lockfd, b' '.join(c) + b'\n')

        os.close(lockfd)
        if os.geteuid() == 0:
            os.chown(self.lock_file, self.uid, self.gid)

        os.rename(self.lock_file, self.cookie_file)

        self.cookieId = cookie_id
        self.cookie = cookie

    def _delete_cookie(self):
        lockfd = self._get_lock()

        cookies = self._get_cookies()

        for i, tpl in enumerate(cookies):
            if int(tpl[0]) == self.cookieId:
                del cookies[i]
                break

        if not cookies:
            os.unlink(self.cookie_file)
            os.close(lockfd)
            os.unlink(self.lock_file)
        else:
            for c in cookies:
                os.write(lockfd, b' '.join(c) + b'\n')

            os.close(lockfd)
            if os.geteuid() == 0:
                os.chown(self.lock_file, self.uid, self.gid)

            os.rename(self.lock_file, self.cookie_file)


@implementer(IBusAuthenticationMechanism)
class BusExternalAuthenticator (object):
    """
    Implements the Bus-side portion of the EXTERNAL authentication
    mechanism
    """

    def __init__(self):
        self.ok = False
        self.creds = None

    def getMechanismName(self):
        return 'EXTERNAL'

    def init(self, protocol):
        self.creds = protocol._unix_creds

    def step(self, arg):
        if not self.creds:
            return ('REJECT', 'Unix credentials not available')
        if not self.ok:
            self.ok = True
            return ('CONTINUE', '')
        else:
            return ('OK', None)

    def getUserName(self):
        import pwd
        return pwd.getpwuid(self.creds[1]).pw_name

    def cancel(self):
        pass


@implementer(IBusAuthenticationMechanism)
class BusAnonymousAuthenticator (object):
    """
    Implements the Bus-side portion of the ANONYMOUS authentication
    mechanism
    """

    def getMechanismName(self):
        return 'ANONYMOUS'

    def init(self, protocol):
        pass

    def step(self, arg):
        return ('OK', None)

    def getUserName(self):
        return 'anonymous'

    def cancel(self):
        pass


@implementer(IDBusAuthenticator)
class BusAuthenticator (object):
    """
    Implements the Bus-side portion of the DBus authentication protocol.

    @ivar authenticators: A dictionary of mechanism names to mechanism
                          implementation classes
    @type authenticators: C{dict}
    """

    MAX_REJECTS_ALLOWED = 5

    authenticators = {b'EXTERNAL': BusExternalAuthenticator,
                      b'DBUS_COOKIE_SHA1': BusCookieAuthenticator,
                      b'ANONYMOUS': BusAnonymousAuthenticator}

    def __init__(self, server_guid):
        self.server_guid = server_guid
        self.authenticated = False
        self.mechanisms = {}
        self.protocol = None
        self.guid = None

        self.reject_count = 0
        self.state = None
        self.current_mech = None

        for n, m in six.iteritems(self.authenticators):
            self.mechanisms[n] = m

        mechNames = self.authenticators.keys()

        self.reject_msg = b'REJECTED ' + b' '.join(mechNames)

    def beginAuthentication(self, protocol):
        self.protocol = protocol
        self.state = 'WaitingForAuth'

    def handleAuthMessage(self, line):
        # print 'RCV: ', line.rstrip()
        if b' ' not in line:
            cmd = line
            args = b''
        else:
            cmd, args = line.split(b' ', 1)
        m = getattr(self, '_auth_' + cmd.decode(), None)
        if m:
            m(args)
        else:
            self.sendError(b'"Unknown command"')

    def authenticationSucceeded(self):
        return self.authenticated

    def getGUID(self):
        return self.guid

    # --------------------------------------------------

    def reject(self):
        if self.current_mech:
            self.current_mech.cancel()
            self.current_mech = None

        self.reject_count += 1
        if self.reject_count > self.MAX_REJECTS_ALLOWED:
            raise DBusAuthenticationFailed(
                'Client exceeded maximum failed authentication attempts')

        self.sendAuthMessage(self.reject_msg)
        self.state = 'WaitingForAuth'

    def sendAuthMessage(self, msg):
        # print 'SND: ', msg.rstrip()
        self.protocol.sendAuthMessage(msg)

    def sendError(self, msg=None):
        if msg:
            self.sendAuthMessage(b'ERROR ' + msg)
        else:
            self.sendAuthMessage(b'ERROR')

    def stepAuth(self, response):
        if self.current_mech is None:
            self.reject()
            return

        if response:
            response = binascii.unhexlify(response.strip()).decode('ascii')

        status, challenge = self.current_mech.step(response)

        if status == 'OK':
            self.sendAuthMessage(b'OK ' + self.server_guid)
            self.state = 'WaitingForBegin'

        elif status == 'CONTINUE':
            self.sendAuthMessage(b'DATA ' + binascii.hexlify(challenge))
            self.state = 'WaitingForData'

        else:
            # print 'REJECT: ', status
            self.reject()

    def _auth_AUTH(self, line):
        if self.state == 'WaitingForAuth':
            tpl = line.split()

            if len(tpl) == 0:
                self.reject()
            else:
                mech = tpl[0]
                initial_response = None
                if len(tpl) > 1:
                    initial_response = tpl[1]
                if mech in self.mechanisms:
                    m = self.mechanisms[mech]()
                    self.current_mech = IBusAuthenticationMechanism(m)
                    self.current_mech.init(self.protocol)
                    self.stepAuth(initial_response)
                else:
                    self.reject()

        else:
            self.sendError()

    def _auth_BEGIN(self, line):
        if self.state == 'WaitingForBegin':
            self.authenticated = True
            self.guid = self.current_mech.getUserName()
            self.current_mech = None
        else:
            raise DBusAuthenticationFailed('Protocol violation')

    def _auth_ERROR(self, line):
        if self.state in ('WaitingForAuth', 'WaitingForData',
                          'WaitingForBegin'):
            self.reject()

    def _auth_DATA(self, line):
        if self.state == 'WaitingForData':
            self.stepAuth(line)
        else:
            self.sendError()

    def _auth_CANCEL(self, line):
        if self.state in ('WaitingForData', 'WaitingForBegin'):
            self.reject()
        else:
            self.sendError()

    def _auth_NEGOTIATE_UNIX_FD(self, line):
        # Only valid in the 'WaitingForBegin' state
        self.sendError()
