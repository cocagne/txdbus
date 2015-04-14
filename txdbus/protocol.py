"""
This module implements the wire-level DBus protocol.

@author: Tom Cocagne
"""
import struct
import os.path

from   zope.interface import Interface

from   twisted.internet import protocol, defer, error
from   twisted.python import log

from txdbus import message, error

_is_linux = False

if os.path.exists('/proc/version'):
    with open('/proc/version') as f:
        if f.read().startswith('Linux'):
            _is_linux = True


class IDBusAuthenticator (Interface):
    """
    Classes implementing this interface may be used by L{BasicDBusProtocol}
    instances to handle authentication
    """

    def beginAuthentication(self, protocol):
        """
        Called immediately after the connection is established.

        @type protocol: L{BasicDBusProtocol}
        @param protocol: L{BasicDBusProtocol} instance requiring authentication
        """
        
    def handleAuthMessage(self, line):
        """
        Handles an authentication message received on the connection. The
        authentication delimeter will be stripped prior to calling this
        method. If authentication fails, this method should raise
        L{error.DBusAuthenticationFailed} with an error message describing
        the reason.
        """

    def authenticationSucceeded(self):
        """
        @rtype: C{bool}
        @returns: True if authentication has succeeded
        """

    def getGUID(self):
        """
        @rtype: C{string}
        @returns: the GUID for the successfully authenticated connection
        """




class BasicDBusProtocol(protocol.Protocol):
    """
    Basic class providing support for converting a stream of bytes into
    authentication and DBus messages. This class is not inteded for
    direct use.

    @ivar authenticator: Class used to authenticate connections
    @type authenticator: Class implementing L{IDBusAuthenticator}
    """
    _buffer         = b''
    _authenticated  = False
    _nextMsgLen     = 0
    _endian         = '<'
    _client         = True
    _firstByte      = True
    _unix_creds     = None # (pid, uid, gid) from UnixSocket credential passing
    authenticator   = None # Class to handle DBus authentication
    authDelimiter   = b'\r\n'
    MAX_AUTH_LENGTH = 16384
    MAX_MSG_LENGTH  = 2**27
    MSG_HDR_LEN     = 16 # including 4-byte padding for array of structure

    guid = None # Filled in with the GUID of the server (for client protocol)
                # or the username of the authenticated client (for server protocol)

    def connectionMade(self):

        self.guid = None
        
        if self._client:
            # DBus specification requires that clients send a null byte upon connection
            # to the bus
            self.transport.write(b'\0')


        if self._client:
            self._dbusAuth = IDBusAuthenticator(self.authenticator())
        else:
            self._dbusAuth = IDBusAuthenticator(self.authenticator(
                                                       self.factory.bus.uuid ))
        self._dbusAuth.beginAuthentication(self)
        


    def dataReceived(self, data):
        
        if self._authenticated:
            self._buffer = self._buffer + data
            buffer_len = len(self._buffer)
            
            if self._nextMsgLen == 0 and buffer_len >= 16:
                # There would be multiple clients using different endians.
                # Reset endian every time.
                if self._buffer[:1] != b'l':
                    self._endian = '>'
                else:
                    self._endian = '<'

                body_len = struct.unpack(self._endian + 'I', self._buffer[4:8]  )[0]
                harr_len = struct.unpack(self._endian + 'I', self._buffer[12:16])[0]

                hlen = self.MSG_HDR_LEN + harr_len

                padlen = hlen % 8 and (8 - hlen%8) or 0

                self._nextMsgLen = self.MSG_HDR_LEN + harr_len + padlen + body_len


            if self._nextMsgLen != 0 and buffer_len >= self._nextMsgLen:
                raw_msg      = self._buffer[:self._nextMsgLen]
                self._buffer = self._buffer[self._nextMsgLen:]

                self._nextMsgLen = 0
                
                self.rawDBusMessageReceived(raw_msg)
                
                if self._buffer:
                    # Recursively process any other complete messages
                    self.dataReceived(b'')
        else:
            if not self._client and self._firstByte:
                if not data[0] == '\0':
                    self.transport.loseConnection()
                    return
                self._firstByte = False
                data = data[1:]
                
                if _is_linux:
                    import socket
                    cd = self.transport.socket.getsockopt(socket.SOL_SOCKET,
                                                          17, # SO_PEERCRED
                                                          struct.calcsize('3i')
                                                          )
                    self._unix_creds = struct.unpack('3i',cd)

                
            lines  = (self._buffer+data).split(self.authDelimiter)
            self._buffer = lines.pop(-1)
            for line in lines:
                if self.transport.disconnecting:
                    # this is necessary because the transport may be
                    # told to lose the connection by a line within a
                    # larger packet, and it is important to disregard
                    # all the lines in that packet following the one
                    # that told it to close.
                    return
                if len(line) > self.MAX_AUTH_LENGTH:
                    return self.authMessageLengthExceeded(line)
                else:
                    try:
                        self._dbusAuth.handleAuthMessage(line)
                        if self._dbusAuth.authenticationSucceeded():
                            self.guid = self._dbusAuth.getGUID()
                            self._dbusAuth = None
                            self.setAuthenticationSucceeded()
                            if self._buffer:
                                self.dataReceived(b'')
                    except error.DBusAuthenticationFailed as e:
                        log.msg('DBus Authentication failed: ' + str(e))
                        self.transport.loseConnection()
            else:
                if len(self._buffer) > self.MAX_AUTH_LENGTH:
                    return self.authMessageLengthExceeded(self._buffer)
            

    #--------------------------------------------------------------------------
    # Authentication Message Handling
    #
    
    def sendAuthMessage(self, msg):
        """
        Sends a message to the other end of the connection.

        @param msg: The line to send, not including the authDelimiter.
        @type msg: C{str}
        """
        return self.transport.writeSequence((msg, self.authDelimiter))


    def authMessageLengthExceeded(self, line):
        """
        Called when the maximum line length has been reached. By default,
        this method simply terminates the connection.
        """
        self.transport.loseConnection()

        
    def setAuthenticationSucceeded(self):
        """
        Called by subclass when the authentication process completes. This
        causes the protocol to switch from line-based authentication messaging
        to binary DBus message handling
        """
        self._authenticated = True
        self.connectionAuthenticated()

        
    def connectionAuthenticated(self):
        """
        Called when the connection has been successfully authenticated
        """

    #--------------------------------------------------------------------------
    # DBus Message Handling
    #
    def sendMessage(self, msg):
        """
        @type msg: L{message.DBusMessage}
        @param msg: A L{message.DBusMessage} instance to send over the connection
        """
        assert isinstance(msg, message.DBusMessage)
        self.transport.write( msg.rawMessage )
        
    
    def rawDBusMessageReceived(self, rawMsg):
        """
        Called when the raw bytes for a complete DBus message are received

        @param rawMsg: Byte-string containing the complete message
        @type rawMsg: C{str}
        """
        m  = message.parseMessage( rawMsg )
        mt = m._messageType
            
        if mt == 1:
            self.methodCallReceived( m )
        elif mt == 2:
            self.methodReturnReceived( m )
        elif mt == 3:
            self.errorReceived( m )
        elif mt == 4:
            self.signalReceived( m )


    def methodCallReceived(self, mcall):
        """
        Called when a DBus METHOD_CALL message is received
        """

    
    def methodReturnReceived(self, mret):
        """
        Called when a DBus METHOD_RETURN message is received
        """

    
    def errorReceived(self, merr):
        """
        Called when a DBus ERROR message is received
        """

    
    def signalReceived(self, msig):
        """
        Called when a DBus METHOD_CALL message is received
        """
