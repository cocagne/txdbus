
"""
This is a DBus client connection implementation. It provides the ability to call
methods on remote objects, receive signals, and export local objects and methods
over the DBus bus.

@author: Tom Cocagne
"""

import os
import sys

from twisted.internet import reactor, defer
from twisted.internet.protocol import Factory
from twisted.internet.error import ConnectError

import txdbus.protocol

from txdbus import authentication, message, objects, introspection, router
from txdbus import error


# Constant return values for requestBusName
NAME_ACQUIRED      = 1
NAME_IN_QUEUE      = 2
NAME_IN_USE        = 3
NAME_ALREADY_OWNER = 4


# Constant return values for releaseBusName
NAME_RELEASED      = 1
NAME_NON_EXISTENT  = 2
NAME_NOT_OWNER     = 3


# unique constant for signature checking
_NO_CHECK_RETURN   = '__DBUS_NO_RETURN_VALUE'



class DBusClientConnection (txdbus.protocol.BasicDBusProtocol):
    """
    Client-side implementation of the DBus Protocol.

    @ivar authenticator: Class to used to authenticate connections
    @type authenticator: Class implementing L{protocol.IDBusAuthenticator}

    @ivar busName: Unique name of the connection to the bus
    @type busName: C{string}
    """
    authenticator = authentication.ClientAuthenticator

    busName = None
    
    def connectionAuthenticated(self):
        """
        Called by L{protocol.BasicDBusProtocol} when the DBus authentication
        has completed successfully.
        """
        self.router        = router.MessageRouter()
        self.match_rules   = dict()
        self.objHandler    = objects.DBusObjectHandler(self)
        self._pendingCalls = dict() # serial_number => (deferred, delayed_timeout_cb | None)
        self._dcCallbacks  = list()

        d = self.callRemote( '/Hello', 'Hello',
                             interface   = 'org.freedesktop.DBus',
                             destination = 'org.freedesktop.DBus' )

        d.addCallbacks( self._cbGotHello,
                        lambda err: self.factory._failed(err) )

    
    def _cbGotHello(self, busName):
        """
        Called in reply to the initial Hello remote method invocation
        """
        self.busName = busName
        
        #print 'Connection Bus Name = ', self.busName
        
        self.factory._ok(self)


    def disconnect(self):
        """
        Terminates the connection to the DBus Daemon
        """
        self.transport.loseConnection()


    def connectionLost(self, reason):
        """
        Called when the transport loses connection to the bus
        """
        if self.busName is None:
            return

        for cb in self._dcCallbacks:
            cb(self, reason)
        
        for d, timeout in self._pendingCalls.values():
            if timeout:
                timeout.cancel()
            d.errback(reason)
        self._pendingCalls = dict()

        self.objHandler.connectionLost(reason)


    def notifyOnDisconnect(self, callback):
        """
        @type callback: Callable object a that accepts a
        L{DBusClientConnection} and L{twisted.python.failure.Failure}
        @param callback: Function that will be called when the connection to
                         the DBus session is lost. Arguments are the
                         L{DBusClientConnection} that lost connection and
                         the reason for the disconnect. This is the same value
                         passed to
                         L{twisted.internet.protocol.Protocol.connectionLost})                         
        """
        self._dcCallbacks.append(callback)


    
    def cancelNotifyOnDisconnect(self, callback):
        """
        Cancels a callback previously registered with notifyOnDisconnect
        """
        self._dcCallbacks.remove(callback)


    def exportObject(self, dbusObject):
        """
        Exports an object over DBus

        @type dbusObject: An object implementing the L{objects.IDBusObject}
                          interface
        @param dbusObject: Object to make available for remote access via DBus
        """
        self.objHandler.exportObject(dbusObject)


    def unexportObject(self, objectPath):
        """
        Stops exporting an object over DBus

        @type objectPath: C{string}
        @param objectPath: Object to stop exporting
        """
        self.objHandler.unexportObject(objectPath)

    
    def getRemoteObject(self, busName, objectPath, interfaces=None,
                        replaceKnownInterfaces = False):
        """
        Creates a L{objects.RemoteDBusObject} instance to represent the
        specified DBus object.  If explicit interfaces are not supplied, DBus
        object introspection will be used to obtain them automatically.

        @param interfaces: May be None, a single value, or a list of string
                           interface names and/or instances of
                           L{interface.DBusInterface}. If None or any of the
                           specified interface names are unknown, full
                           introspection will be attempted.  If interfaces
                           consists of solely of L{interface.DBusInterface}
                           instances and/or known interface names, no
                           introspection will be preformed.

        @rtype: L{twisted.internet.defer.Deferred}
        @returns: A deferred to a L{objects.RemoteDBusObject} instance representing
                  the remote object
        """
        return self.objHandler.getRemoteObject( busName, objectPath, interfaces,
                                                 replaceKnownInterfaces)


    def delMatch(self, rule_id):
        """
        Removes a message matching rule previously registered with addMatch
        """
        rule = self.match_rules[rule_id]
        
        d = self.callRemote('/org/freedesktop/DBus', 'RemoveMatch',
                            interface   = 'org.freedesktop.DBus',
                            destination = 'org.freedesktop.DBus',
                            body        = [rule],
                            signature   = 's')

        def ok(_):
            del self.match_rules[rule_id]
            self.router.delMatch(rule_id)

        d.addCallback(ok)

        return d

        
    def addMatch(self, callback, mtype=None, sender=None, interface=None,
                 member=None, path=None, path_namespace=None, destination=None,
                 arg=None, arg_path=None, arg0namespace=None):
        """
        Creates a message matching rule, associates it with the specified
        callback function, and sends the match rule to the DBus daemon.
        The arguments to this function are exactly follow the DBus specification.
        Refer to the \"Message Bus Message Routing\" section of the DBus
        specification for details.

        @rtype: C{int}
        @returns: a L{Deferred} to an integer id that may be used to unregister the match rule
        """

        l = list()

        def add( k,v ):
            if v is not None:
                l.append( "%s='%s'" % (k,v) )

        add('type',           mtype)
        add('sender',         sender)
        add('interface',      interface)
        add('member',         member)
        add('path',           path)
        add('path_namespace', path_namespace)
        add('destination',    destination)

        if arg:
            for idx, v in arg:
                add('arg%d' % (idx,), v)

        if arg_path:
            for idx, v in arg_path:
                add('arg%dpath' % (idx,), v)

        add('arg0namespace', arg0namespace)

        rule = ','.join(l)

        d = self.callRemote('/org/freedesktop/DBus', 'AddMatch',
                            interface   = 'org.freedesktop.DBus',
                            destination = 'org.freedesktop.DBus',
                            body        = [rule],
                            signature   = 's')

        def ok(_):
            rule_id = self.router.addMatch(callback, mtype, sender, interface,
                                           member, path, path_namespace, destination,
                                           arg, arg_path, arg0namespace)
            self.match_rules[rule_id] = rule
            return rule_id

        d.addCallbacks( ok )

        return d


    def getNameOwner(self, busName):
        """
        Calls org.freedesktop.DBus.GetNameOwner
        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to the unique connection name owning the bus name
        """
        d = self.callRemote('/org/freedesktop/DBus', 'GetNameOwner',
                            interface   = 'org.freedesktop.DBus',
                            signature   = 's',
                            body        = [busName],
                            destination = 'org.freedesktop.DBus'
                            )
        return d

    
    def getConnectionUnixUser(self, busName):
        """
        Calls org.freedesktop.DBus.GetConnectionUnixUser
        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to the integer unix user id
        """
        d = self.callRemote('/org/freedesktop/DBus', 'GetConnectionUnixUser',
                            interface   = 'org.freedesktop.DBus',
                            signature   = 's',
                            body        = [busName],
                            destination = 'org.freedesktop.DBus'
                            )
        return d

    
    def listQueuedBusNameOwners(self, busName):
        """
        Calls org.freedesktop.DBus.ListQueuedOwners
        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to a list of unique bus names for connections queued
                  for the name
        """
        d = self.callRemote('/org/freedesktop/DBus', 'ListQueuedOwners',
                            interface   = 'org.freedesktop.DBus',
                            signature   = 's',
                            body        = [busName],
                            destination = 'org.freedesktop.DBus'
                            )
        return d


    def releaseBusName(self, busName):
        """
        Calls org.freedesktop.DBus.ReleaseName
        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to an integer constant which will be one of
                  NAME_RELEASED, NAME_NON_EXISTENT, NAME_NOT_OWNER
        """
        d = self.callRemote('/org/freedesktop/DBus', 'ReleaseName',
                            interface   = 'org.freedesktop.DBus',
                            signature   = 's',
                            body        = [busName],
                            destination = 'org.freedesktop.DBus'
                            )
        return d


    def requestBusName(self, newName,
                       allowReplacement      = False,
                       replaceExisting       = False,
                       doNotQueue            = True,
                       errbackUnlessAcquired = True):
        """
        Calls org.freedesktop.DBus.RequestName to request that the specified
        bus name be associated with the connection.

        @type newName: C{string}
        @param newName: Bus name to acquire

        @type allowReplacement: C{bool}
        @param allowReplacement: If True (defaults to False) and another application
                                 later requests this same name, the new requester
                                 will be given the name and this connection will
                                 lose ownership.

        @type replaceExisting: C{bool}
        @param replaceExisting: If True (defaults to False) and another application
                                owns the name but specified allowReplacement at the
                                time of the name acquisition, this connection will
                                assume ownership of the bus name.

        @type doNotQueue: C{bool}
        @param doNotQueue: If True (defaults to True) the name request will fail if
                           the name is currently in use. If False, the request will
                           cause this connection to be queued for ownership of the
                           requested name

        @type errbackUnlessAcquired: C{bool}
        @param errbackUnlessAcquired: If True (defaults to True) an
                                      L{twisted.python.failure.Failure} will be
                                      returned if the name is not acquired.
        
        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to 
        """
        flags = 0
        if allowReplacement:
            flags |= 0x1
        if replaceExisting:
            flags |= 0x2
        if doNotQueue:
            flags |= 0x4

        d = self.callRemote('/org/freedesktop/DBus', 'RequestName',
                            interface   = 'org.freedesktop.DBus',
                            signature   = 'su',
                            body        = [newName, flags],
                            destination = 'org.freedesktop.DBus'
                            )

        def on_result( r ):
            if errbackUnlessAcquired and not ( r == NAME_ACQUIRED or r == NAME_ALREADY_OWNER):
                raise error.FailedToAcquireName( newName, r )
            return r

        d.addCallback(on_result)
            
        return d

    
    def introspectRemoteObject(self, busName, objectPath,
                               replaceKnownInterfaces=False):
        """
        Calls org.freedesktop.DBus.Introspectable.Introspect

        @type busName: C{string}
        @param busName: Name of the bus containing the object

        @type objectPath: C{string}
        @param objectPath: Object Path to introspect
        
        @type replaceKnownInterfaces: C{bool}
        @param replaceKnownInterfaces: If True (defaults to False), the content of
                                       the introspected XML will override any
                                       pre-existing definitions of the contained
                                       interfaces.

        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to a list of L{interface.DBusInterface} instances
                  created from the content of the introspected XML
                  description of the object's interface.
        """
        d = self.callRemote(objectPath, 'Introspect',
                            interface   = 'org.freedesktop.DBus.Introspectable',
                            destination = busName)

        def ok( xml_str ):
            return introspection.getInterfacesFromXML(xml_str, replaceKnownInterfaces)

        def err(e):
            raise error.IntrospectionFailed('Introspection Failed: ' + e.getErrorMessage())

        d.addCallbacks( ok, err )

        return d


    def _cbCvtReply(self, msg, returnSignature):
        """
        Converts a remote method call reply message into an appropriate callback
        value.
        """
        if msg is None:
            return None

        if returnSignature != _NO_CHECK_RETURN:
            if not returnSignature:
                if msg.signature:
                    raise error.RemoteError('Unexpected return value signature')
            else:
                if not msg.signature or msg.signature != returnSignature:
                    msg = 'Expected "%s". Received "%s"' % (str(returnSignature), str(msg.signature))
                    raise error.RemoteError('Unexpected return value signature: %s' % (msg,))
            
        if msg.body is None or len(msg.body) == 0:
            return None

        #if not (isinstance(msg.body[0],basestring) and msg.body[0].startswith('<!D')):
        #    print 'RET SIG', msg.signature, 'BODY:', msg.body
        if len(msg.body) == 1 and not msg.signature[0] == '(':
            return msg.body[0]
        else:
            return msg.body
        

    def callRemote(self, objectPath, methodName,
                   interface        = None,
                   destination      = None,
                   signature        = None,
                   body             = None,
                   expectReply      = True,
                   autoStart        = True,
                   timeout          = None,
                   returnSignature  = _NO_CHECK_RETURN):
        """
        Calls a method on a remote DBus object and returns a deferred to the result.

        @type objectPath: C{string}
        @param objectPath: Path of the remote object

        @type methodName: C{string}
        @param methodName: Name of the method to call

        @type interface: None or C{string}
        @param interface: If specified, this specifies the interface containing the
                          desired method

        @type destination: None or C{string}
        @param destination: If specified, this specifies the bus name containing
                            the remote object

        @type signature: None or C{string}
        @param signature: If specified, this specifies the DBus signature of the
                          body of the DBus MethodCall message. This string must
                          be a valid Signature string as defined by the DBus
                          specification. If arguments are supplied to the method
                          call, this parameter must be provided.

        @type body: C{list}
        @param body: A C{list} of Python objects to encode. The list content must
                     match the content of the signature parameter

        @type expectReply: C{bool}
        @param expectReply: If True (defaults to True) the returned deferred will
                            be called back with the eventual result of the remote
                            call. If False, the deferred will be immediately called
                            back with None.

        @type autoStart: C{bool}
        @param autoStart: If True (defaults to True) DBus will attempt to
                          automatically start a service to handle the method
                          call if a service matching the target object is registered
                          but not yet started.

        @type timeout: None or C{float}
        @param timeout: If specified and the remote call does not return a value
                        before the timeout expires, the returned Deferred will be
                        errbacked with a L{error.TimeOut} instance.

        @type returnSignature: C{string}
        @param returnSignature: If specified, the return values will be validated
                                against the signature string. If the returned values
                                do not mactch, the returned Deferred witl be
                                errbacked with a L{error.RemoteError} instance.
        
        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to the result. If expectReply is False, the deferred
                  will be immediately called back with None.
        """

        try:
            mcall = message.MethodCallMessage( objectPath, methodName,
                                               interface    = interface,
                                               destination  = destination,
                                               signature    = signature,
                                               body         = body,
                                               expectReply  = expectReply,
                                               autoStart    = autoStart )
            
            d = self.callRemoteMessage( mcall, timeout )

            d.addCallback( self._cbCvtReply, returnSignature )

            return d
        except Exception as e:
            return defer.fail()


    def _onMethodTimeout(self, serial, d):
        """
        Called when a remote method invocation timeout occurs
        """
        del self._pendingCalls[ serial ]
        d.errback(error.TimeOut('Method call timed out'))
        
    
    def callRemoteMessage(self, mcall, timeout = None):
        """
        Uses the specified L{message.MethodCallMessage} to call a remote method.

        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to the result of the remote method call
        """
        assert isinstance(mcall, message.MethodCallMessage)
        
        if mcall.expectReply:
            d = defer.Deferred()

            if timeout:
                timeout = reactor.callLater(timeout, self._onMethodTimeout, mcall.serial, d)

            self._pendingCalls[ mcall.serial ] = (d, timeout)

            self.sendMessage( mcall )

            return d
        else:
            self.sendMessage( mcall )

            return defer.succeed(None)


    
    def methodCallReceived(self, mcall):
        """
        Called when a method call message is received
        """
        self.objHandler.handleMethodCallMessage(mcall)
        
            
    def methodReturnReceived(self, mret):
        """
        Called when a method return message is received
        """
        d, timeout = self._pendingCalls.get(mret.reply_serial, (None,None))
        if timeout:
            timeout.cancel()
        if d:
            del self._pendingCalls[ mret.reply_serial ]
            d.callback(mret)

            
    def errorReceived(self, merr):
        """
        Called when an error message is received
        """
        d, timeout = self._pendingCalls.get(merr.reply_serial, (None,None))
        if timeout:
            timeout.cancel()
        if d:
            del self._pendingCalls[ merr.reply_serial ]
            e = error.RemoteError( merr.error_name )
            e.message = ''
            e.values  = []
            if merr.body:
                if isinstance(merr.body[0], basestring):
                    e.message = merr.body[0]
                e.values = merr.body
            d.errback( e )

            
    def signalReceived(self, msig):
        """
        Called when a signal message is received
        """
        self.router.routeMessage(msig)
        
            


                
class DBusClientFactory (Factory):
    """
    Factory for DBusClientConnection instances
    """
    protocol = DBusClientConnection

    def __init__(self):
        self.d = defer.Deferred()

    def _ok(self, proto):
        self.d.callback( proto )

    def _failed(self, err):
        self.d.errback(err)

    def getConnection(self):
        """
        @rtype: L{twisted.internet.defer.Deferred}
        @returns: A Deferred to the fully-connected L{DBusClientConnection}
                  instance. This method should be used to obtain a reference
                  to the L{DBusClientConnection} as it will be called back/error
                  backed after authentication and DBus session registration are
                  complete.
        """
        return self.d



        
def connect( reactor,  busAddress='session' ):
    """
    Connects to the specified bus and returns a
    L{twisted.internet.defer.Deferred} to the fully-connected
    L{DBusClientConnection}. 

    @param reactor: L{twisted.internet.interfaces.IReactor} implementor
    
    @param busAddress: 'session', 'system', or a valid bus address as defined by
                       the DBus specification. If 'session' (the default) or 'system'
                       is supplied, the contents of the DBUS_SESSION_BUS_ADDRESS or
                       DBUS_SYSTEM_BUS_ADDRESS environment variables will be used for
                       the bus address, respectively. If DBUS_SYSTEM_BUS_ADDRESS is not
                       set, the well-known address unix:path=/var/run/dbus/system_bus_socket
                       will be used.
    @type busAddress: C{string}

    @rtype: L{DBusClientConnection}
    @returns: Deferred to L{DBusClientConnection} 
    """
    from txdbus import endpoints

    f = DBusClientFactory()

    d = f.getConnection()

    eplist = endpoints.getDBusEndpoints(reactor, busAddress)

    eplist.reverse()

    def try_next_ep(err):
        if eplist:
            eplist.pop().connect(f).addErrback( try_next_ep )
        else:
            d.errback(ConnectError(string='Failed to connect to any bus address. Last error: ' + err.getErrorMessage()))

    if eplist:
        try_next_ep(None)
    else:
        d.errback(ConnectError(string='Failed to connect to any bus address. No valid bus addresses found'))

    return d
    
    
