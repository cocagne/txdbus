"""
DBus Bus implementation

@author: Tom Cocagne
"""

import os
import binascii

from twisted.internet.protocol import Factory
from twisted.python import log

import txdbus.protocol

from txdbus import authentication, router, message, objects, client, error
from txdbus import marshal
from txdbus.interface import DBusInterface, Method, Signal


class DError(Exception):
    """
    Used to signal anticipated errors 
    """

    def __init__(self, errorName, msg=None):
        self.dbusErrorName = errorName
        self.errorName     = errorName
        self.errorMessage  = msg

    def __str__(self):
        return self.errorMessage


class BusProtocol (txdbus.protocol.BasicDBusProtocol):
    """
    Instances of this class handle connections to DBus clients

    @ivar bus: The L{Bus} instance associated with this connection
    @type bus: L{Bus}
    """
    _client       = False
    _called_hello = False
    bus           = None
    authenticator = authentication.BusAuthenticator

    
    def connectionAuthenticated(self):
        self.username     = self.guid
        self.uniqueName   = None
        self.busNames     = dict() # name => allow_replacement
        self.bus          = self.factory.bus
        self.matchRules   = set()
        self.isConnected  = True 
        

    def connectionLost(self, reason):
        self.isConnected = False
        if self.bus is not None:
            self.bus.clientDisconnected(self)

        
    def rawDBusMessageReceived(self, raw_msg):
        msg = message.parseMessage( raw_msg )
        mt  = msg._messageType
        
        if not self.uniqueName:
            self.bus.clientConnected(self)

        if not self._called_hello and mt == 1:
            if msg.destination == 'org.freedesktop.DBus':
                if msg.member == 'Hello':
        
                    r = message.MethodReturnMessage( msg.serial,
                                           body        = [ self.uniqueName ],
                                           signature   = 's' )

                    self._called_hello = True
                    self.sendMessage( r )
        
                    return

            else:
                self.transport.loseConnection()
                
        msg.sender = self.uniqueName

        msg._marshal(False) # re-marshal with the sender set and same serial number

        self.bus.messageReceived( self, msg )
        


class Bus (objects.DBusObject):
    """
    DBus Bus implementation.

    @ivar stdIface: L{interface.DBusInterface} containing the standard bus interface
    @type stdIface: L{interface.DBusInterface}
    """
    stdIface = DBusInterface( 'org.freedesktop.DBus',
               Method('Hello',                 arguments='',   returns='s' ),
               Method('GetId',                 arguments='',   returns='s' ),
               Method('RequestName',           arguments='su', returns='u' ),
               Method('ReleaseName',           arguments='s',  returns='u' ),
               Method('ListQueuedOwners',      arguments='s',  returns='as'), 
               Method('AddMatch',              arguments='s',  returns=''  ),
               Method('RemoveMatch',           arguments='s',  returns=''  ),
               Method('GetNameOwner',          arguments='s',  returns='s' ),
               Method('GetConnectionUnixUser', arguments='s',  returns='u' ),

               #Not Implemented Methods
               Method('GetConnectionUnixProcessId' , arguments='s',     returns='u' ),
               Method('ListActivatableNames',        arguments='',      returns='as'),
               Method('UpdateActivationEnvironment', arguments='a{ss}', returns=''),
               Method('StartServiceByName',          arguments='su',    returns='u'),
               Method('GetAdtAuditSessionData',      arguments='s',     returns='u'),
               Method('GetConnectionSELinuxSecurityContext', arguments='su', returns='ay'),
               Method('ReloadConfig'),
                            
               Signal('NameAcquired',     arguments='s'),
               Signal('NameLost',         arguments='s'),
               Signal('NameOwnerChanged', arguments='sss')
             )

    dbusInterfaces = [stdIface]
    
    def __init__(self):
        objects.DBusObject.__init__(self, '/org/freedesktop/DBus')
        self.uuid        = binascii.hexlify(os.urandom(16))
        self.clients     = dict() # maps unique_bus_id to client connection
        self.busNames    = dict() # maps name to list of queued connections
        self.router      = router.MessageRouter()
        self.next_id     = 1
        self.obj_handler = objects.DBusObjectHandler(self)

        self.obj_handler.exportObject(self)
        

    # returns the new unique bus name for the client connection
    def clientConnected(self, proto):
        """
        Called when a client connects to the bus. This method assigns the
        new connection a unique bus name.
        """
        proto.uniqueName = ':1.%d' % (self.next_id,)
        self.next_id += 1
        self.clients[ proto.uniqueName ] = proto

        
    def clientDisconnected(self, proto):
        """
        Called when a client disconnects from the bus
        """
        for rule_id in proto.matchRules:
            self.router.delMatch(rule_id)
            
        for busName in proto.busNames.iterkeys():
            self.dbus_ReleaseName(busName, proto.uniqueName)

        if proto.uniqueName:
            del self.clients[ proto.uniqueName ]


    def sendMessage(self, msg):
        """
        Sends the supplied message to the correct destination. The 
        @type msg: L{message.DBusMessage}
        @param msg: The 'destination' field of the message must be set for
                    method calls and returns
        """
        if msg._messageType in (1,2):
            assert msg.destination, 'Failed to specify a message destination'
            
        if msg.destination is not None:
            if msg.destination[0] == ':':
                p = self.clients.get(msg.destination, None)
            else:
                p = self.busNames.get(msg.destination , None)
                if p:
                    p = p[0]

            #print 'SND: ', msg._messageType, ' to ',  p.uniqueName, 'serial', msg.serial, 

            if p:
                p.sendMessage( msg )
            else:
                log.msg('Invalid bus name in msg.destination: ' + msg.destination)
        else:
            self.router.routeMessage(msg)
            

    def messageReceived(self, p, msg):
        mt = msg._messageType

        #print 'MSG: ', mt, ' from ', p.uniqueName, ' to ', msg.destination

        try:
            if mt == 1:
                self.methodCallReceived(p, msg)
            elif mt == 2:
                self.methodReturnReceived(p, msg)
            elif mt == 3:
                self.errorReceived(p, msg)
            elif mt == 4:
                self.signalReceived(p, msg)
                
            if msg.destination and not msg.destination == 'org.freedesktop.DBus':
                self.sendMessage( msg )

            self.router.routeMessage(msg)
        except DError as e:
            sig  = None
            body = None
            if e.errorMessage:
                sig = 's'
                body = [e.errorMessage]
                
            r = message.ErrorMessage(e.errorName, msg.serial, signature=sig,
                                     body=body)
            p.sendMessage( r )

            
    def methodCallReceived(self, p, msg):
        if msg.destination == 'org.freedesktop.DBus':
            self.obj_handler.handleMethodCallMessage( msg )
        

    def methodReturnReceived(self, p, msg):
        pass

    def errorReceived(self, p, msg):
        pass

    def signalReceived(self, p, msg):
        pass



    def sendSignal(self, p, member, signature=None, body=None,
                   path='/org/freedesktop/DBus',
                   interface='org.freedesktop.DBus'):
        """
        Sends a signal to a specific connection
        
        @type p: L{BusProtocol}
        @param p: L{BusProtocol} instance to send a signal to

        @type member: C{string}
        @param member: Name of the signal to send

        @type path: C{string}
        @param path: Path of the object emitting the signal. Defaults to
                     'org/freedesktop/DBus'
        
        @type interface: C{string}
        @param interface: If specified, this specifies the interface containing the
                          desired method. Defaults to 'org.freedesktop.DBus'

        @type body: None or C{list}
        @param body: If supplied, this is a list of signal arguments. The contents
                     of the list must match the signature.

        @type signature: None or C{string}
        @param signature: If specified, this specifies the DBus signature of the
                          body of the DBus Signal message. This string must
                          be a valid Signature string as defined by the DBus
                          specification. If the body argumnent is supplied ,\
                          this parameter must be provided.
        """
        if not isinstance(body, (list,tuple)):
            body = [body]
            
        s = message.SignalMessage(path, member, interface,
                                  p.uniqueName, signature, body)
        p.sendMessage(s)

        
    def broadcastSignal(self, member, signature=None, body=None,
                        path='/org/freedesktop/DBus',
                        interface='org.freedesktop.DBus'):
        """
        Sends a signal to all connections with registered interest
        
        @type member: C{string}
        @param member: Name of the signal to send

        @type path: C{string}
        @param path: Path of the object emitting the signal. Defaults to
                     'org/freedesktop/DBus'
        
        @type interface: C{string}
        @param interface: If specified, this specifies the interface containing the
                          desired method. Defaults to 'org.freedesktop.DBus'

        @type body: None or C{list}
        @param body: If supplied, this is a list of signal arguments. The contents
                     of the list must match the signature.

        @type signature: None or C{string}
        @param signature: If specified, this specifies the DBus signature of the
                          body of the DBus Signal message. This string must
                          be a valid Signature string as defined by the DBus
                          specification. If the body argumnent is supplied ,\
                          this parameter must be provided.
        """
        if not isinstance(body, (list,tuple)):
            body = [body]
            
        s = message.SignalMessage(path, member, interface,
                                  None, signature, body)
        self.router.routeMessage(s)

        
    #----------------------------------------------------------------
    # DBus Object Interface
    #
    def dbus_Hello(self, dbusCaller=None):
        raise DError('org.freedesktop.DBus.Error.Failed',
                     'Already handled an Hello message')

    
    def dbus_GetId(self):
        return self.uuid

    
    def dbus_RequestName(self, name, flags, dbusCaller=None):
        caller = self.clients[ dbusCaller ]

        allow_replacement = bool(flags & 0x1)
        replace_existing  = bool(flags & 0x2)
        do_not_queue      = bool(flags & 0x4)

        if not name:
            raise DError('org.freedesktop.DBus.Error.InvalidArgs',
                         'Empty string is not a valid bus name')

        if name[0] == ':':
           raise DError('org.freedesktop.DBus.Error.InvalidArgs',
                        'Cannot acquire a service starting with \':\' such as "%s"' %
                        (name,))

        try:
            marshal.validateBusName(name)
        except error.MarshallingError as e:
            raise DError('org.freedesktop.DBus.Error.InvalidArgs', str(e))


        def signalAcq(old_owner_name):
            self.sendSignal( caller, 'NameAcquired', 's', name )
            self.broadcastSignal('NameOwnerChanged', 'sss',
                                 [name, old_owner_name, caller.uniqueName])
            

        if not name in self.busNames:
            self.busNames[ name ] = [caller,]
            caller.busNames[ name ] =  allow_replacement

            signalAcq( '' )
            
            return client.NAME_ACQUIRED
        else:
            queue = self.busNames[ name ]
            owner = queue[0]

            if owner is caller:
                # Update the replacement flag
                owner.busNames[ name ] = allow_replacement

                return client.NAME_ALREADY_OWNER
            else:
                if not replace_existing:
                    return client.NAME_IN_USE
                
                if owner.busNames[name]:
                    del queue[0]
                    queue.insert(0,caller)
                    del owner.busNames[ name ]
                    caller.busNames[ name ] = allow_replacement
                    self.sendSignal( owner,  'NameLost',     's', name )
                    signalAcq( owner.uniqueName )
                    return client.NAME_ACQUIRED
                else:
                    if do_not_queue:
                        return client.NAME_IN_USE
                    
                    queue.append(caller)
                    caller.busNames[ name ] = allow_replacement
                    
                    return client.NAME_IN_QUEUE


    def dbus_ReleaseName(self, name, dbusCaller=None):
        caller = self.clients[ dbusCaller ]

        queue = self.busNames.get( name, None )

        if queue is None:
            return client.NAME_NON_EXISTENT

        owner = queue[0]

        if not caller is owner:
            return client.NAME_NOT_OWNER

        del queue[0]

        if caller.isConnected:
            self.sendSignal(caller, 'NameLost', 's', name)

        if queue:
            self.sendSignal(queue[0], 'NameAcquired', 's', name)
        else:
            del self.busNames[ name ]

        return client.NAME_RELEASED
            
        

    def dbus_ListQueuedOwners(self, name):
        queue = self.busNames.get(name, None)
        if queue:
            return [ p.uniqueName for p in queue ]
        else:
            raise DError('org.freedesktop.DBus.Error.NameHasNoOwner',
                         'Could not get owners of name \'%s\': no such name' %
                         (name,))
        

    def dbus_AddMatch(self, rule, dbusCaller=None):
        caller = self.clients[ dbusCaller ]

        kwargs = dict( mtype=None, sender=None, interface=None,
                       member=None, path=None, path_namespace=None,
                       destination=None, args=None, arg_paths=None,
                       arg0namespace=None )

        for item in rule.split(','):
            k,v = item.split('=')
            
            value = v[1:-1]
            
            if k == 'type':
                k = 'mtype'
                
            if k in kwargs:
                kwargs[ k ] = value
                
            elif k.startswith('arg'):
                if k.endswith('path'):
                    if kwargs['arg_paths'] is None:
                        kwargs['arg_paths'] = list()
                    kwargs['arg_paths'].append( (int(k[3:-4]),value) )
                else:
                    if kwargs['args'] is None:
                        kwargs['args'] = list()
                    kwargs['args'].append( (int(k[3:]),value) )
                

        self.router.addMatch(caller.sendMessage, **kwargs)


    def dbus_GetNameOwner(self, busName):
        if busName.startswith(':'):
            conn = self.clients.get(busName, None)
        else:
            conn = self.busNames.get(busName, None)
            if conn:
                conn = conn[0]
            
        if conn is None:
            raise DError("org.freedesktop.DBus.Error.NameHasNoOwner",
                         "Could not get UID of name '%s': no such name" %
                         (busName,))

        return conn.uniqueName
    
        
    def dbus_GetConnectionUnixUser(self, busName):
        if busName.startswith(':'):
            conn = self.clients.get(busName, None)
        else:
            conn = self.busNames.get(busName, None)
            if conn:
                conn = conn[0]
            
        if conn is None:
            raise DError("org.freedesktop.DBus.Error.NameHasNoOwner",
                         "Could not get UID of name '%s': no such name" %
                         (busName,))

        try:
            import pwd
            return pwd.getpwnam( conn.username ).pw_uid
        except:
            raise DError('org.freedesktop.DBus.Error',
                         "Unable to determine unix user for bus '%s'" %
                         (busName,) )
            
        

