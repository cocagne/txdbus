"""
This module provides classes for managing local and remote
DBus objects

@author: Tom Cocagne
"""
import inspect
import weakref

from twisted.internet import defer
from zope.interface import Interface, implementer

from txdbus import interface, error, marshal, message, introspection


def isSignatureValid( expected, received ):
    """
    Verifies that the received signature matches the expected value
    """
    if expected:
        if not received or expected != received:
            return False
    else:
        if received:
            return False
    return True



def dbusMethod(interfaceName, methodName):
    def deco(method):
        method._dbusInterface = interfaceName
        method._dbusMethod    = methodName
        return method
    return deco



class DBusProperty(object):

    def __init__(self, dbusPropertyName, interface=None):
        self.pname     = dbusPropertyName
        self.key       = None
        self.interface = interface # Interface name
        self.attr_name = None      # set by DBusObject
        self.iprop     = None      # points to interface.Property instance

    def __get__(self, instance, owner):
        if not hasattr(instance, '_dbusProperties'):
            instance._dbusProperties = dict()

        if self.interface is None:
            # Force object to set it
            instance._getProperty('', self.pname)

        if self.key is None:
            self.key = self.interface + self.pname

        return instance._dbusProperties.get( self.key, None )

    def __set__(self, instance, value):
        
        if not hasattr(instance, '_dbusProperties'):
            instance._dbusProperties = dict()

        if self.iprop is None:
            # Force object to set it
            instance._getProperty('', self.pname)

        if self.key is None:
            self.key = self.interface + self.pname

        instance._dbusProperties[ self.key ] = value

        if self.iprop.emits == 'true':
            instance.emitSignal('PropertiesChanged',
                                self.interface,
                                { self.pname : value },
                                [])

    def __delete__(self, instance):
        raise AttributeError('DBus properties cannot be deleted')



class RemoteDBusObject (object):
    """
    Provides local representation of a remote DBus object.
    """
    _disconnectCBs = None
    _signalRules   = None
    
    
    def __init__(self, objHandler, busName, objectPath, interfaces):
        """
        @type objHandler: L{DBusObjectHandler}
        @param objHandler: L{DBusObjectHandler} managing this instance

        @type busName: C{string}
        @param busName: Name of the bus owning the remote object

        @type objectPath: C{string}
        @param objectPath: Path of the remote object

        @type interfaces: List of C{interface.DBusInterface}
        @param interfaces: List of interfaces supported by the remote object
        """
        self.objHandler    = objHandler
        self.busName       = busName
        self.objectPath    = objectPath
        self.interfaces    = interfaces

        
    
    def notifyOnDisconnect(self, callback):
        """
        Registers a callback that will be called when the DBus connection
        underlying the remote object is lost
        
        @type callback: Callable object accepting a L{RemoteDBusObject} and
                        L{twisted.python.failure.Failure}
        @param callback: Function that will be called when the connection to
                         the DBus session is lost. Arguments are the
                         L{RemoteDBusObject} instance and reason for the
                         disconnect (the same value passed to
                         L{twisted.internet.protocol.Protocol.connectionLost})                         
        """
        if self._disconnectCBs is None:
            self._disconnectCBs = list()
        self._disconnectCBs.append(callback)


    
    def cancelNotifyOnDisconnect(self, callback):
        """
        Cancels a callback previously registered with notifyOnDisconnect
        """
        if self._disconnectCBs:
            self._disconnectCBs.remove(callback)

            
    def connectionLost(self, reason):
        """
        Called by the L{DBusObjectHandler} when the connection is lost
        """
        if self._disconnectCBs:
            for cb in self._disconnectCBs:
                cb(self, reason)

                
    def notifyOnSignal(self, signalName, callback, interface=None):
        """
        Informs the DBus daemon of the process's interest in the specified
        signal and registers the callback function to be called when the
        signal arrives. Multiple callbacks may be registered.
        
        @type signalName: C{string}
        @param signalName: Name of the signal to register the callback for

        @type callback: Callable object
        @param callback: Callback to be called on signal arrival. The callback
                         will be passed signals arguments as positional function
                         arguments.

        @type interface: C{string}
        @param interface: Optional DBus interface emitting the signal. This is
                          only needed if more than one interface shares a
                          signal with the same name

        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to an integer rule_id that may be passed to cancelSignalNotification
                  to prevent the delivery of future signals to the callback
        """
        iface  = None
        signal = None

        for i in self.interfaces:
            if interface and not i.name == interface:
                continue
            
            if signalName in i.signals:
                signal    = i.signals[ signalName ]
                iface = i
                break
        
        def callback_caller( sig_msg ):
            if isSignatureValid( signal.sig, sig_msg.signature ):
                if sig_msg.body:
                    callback( *sig_msg.body )
                else:
                    callback()
        
        
        if iface is None:
            raise AttributeError('Requested signal "%s" is not a member of any of the supported interfaces' %
                                 (signalName,))

        
        d = self.objHandler.conn.addMatch( callback_caller,
                                           mtype     = 'signal',
                                           path      = self.objectPath,
                                           member    = signalName,
                                           interface = iface.name )
        
        def on_ok( rule_id ):

            if self._signalRules is None:
                self._signalRules = set()
                
            self._signalRules.add( rule_id )

            return rule_id

        d.addCallback( on_ok )

        return d


    def cancelSignalNotification(self, rule_id):
        """
        Cancels a callback previously registered with notifyOnSignal
        """
        if self._signalRules and rule_id in self._signalRules:
            self.objHandler.conn.delMatch(rule_id)
            self._signalRules.remove(rule_id)
                                        
    
    def callRemote(self, methodName, *args, **kwargs):
        """
        Calls the remote method and returns a Deferred instance to the result.
        DBus does not support passing keyword arguments over the wire. The
        keyword arguments accepted by this method alter the behavior of the remote
        call as described in the kwargs prameter description.

        @type methodName: C{string}
        @param methodName: Name of the method to call

        @param args: Positional arguments to be passed to the remote method

        @param kwargs: Three keyword parameters may be passed to alter the behavior
                       of the remote method call. If \"expectReply=False\" is
                       supplied, the returned Deferred will be immediately called
                       back with the value None. If \"autoStart=False\" is supplied
                       the DBus daemon will not attempt to auto-start a service to
                       fulfill the call if the service is not yet running (defaults
                       to True). If \"timeout=VALUE\" is supplied, the returned
                       Deferred will be errbacked with a L{error.TimeOut} instance
                       if the remote call does not return before the timeout
                       elapses. If \"interface\" is specified, the remote call
                       use the method of the named interface.

        @rtype: L{twisted.internet.defer.Deferred}
        @returns: a Deferred to the result of the remote call
        """
        expectReply = kwargs.get('expectReply', True)
        autoStart   = kwargs.get('autoStart',   True)
        timeout     = kwargs.get('timeout',     None)
        interface   = kwargs.get('interface',   None)
        
        m = None
        
        for i in self.interfaces:
            if interface and not interface == i.name:
                continue
            m = i.methods.get(methodName, None)
            if m:
                break

        if m is None:
            raise AttributeError('Requested method "%s" is not a member of any of the supported interfaces' %
                                 (methodName,))
        
        if len(args) != m.nargs:
            raise TypeError('%s.%s takes %d arguments (%d given)' % (i.name, methodName, m.nargs, len(args)))
        
        return self.objHandler.conn.callRemote( self.objectPath, methodName,
                                                 interface        = i.name,
                                                 destination      = self.busName,
                                                 signature        = m.sigIn,
                                                 body             = args,
                                                 expectReply      = expectReply,
                                                 autoStart        = autoStart,
                                                 timeout          = timeout,
                                                 returnSignature  = m.sigOut )


    
class IDBusObject (Interface):
    """
    Classes implementing this interface may be exported on DBus.
    """
    
    def getInterfaces(self):
        """
        Returns a iterator of L{interface.DBusInterface} objects implemented by
        the instance
        """

    def getObjectPath(self):
        """
        Returns the DBus object path for this instance
        """

    def setObjectHandler(self, objectHandler):
        """
        Provides the instance with a reference to its L{DBusObjectHandler} instance
        
        @type objectHandler: L{DBusObjectHandler}
        @param objectHandler: Thte L{DBusObjectHandler} managing this instance
        """
        

    def executeMethod(self, interfaceObj, methodName, methodArguments, sender):
        """
        Invokes the named method and returns the results. The method may return
        the result immediately or may return a deferred.
        
        @type interfaceObj: L{interface.DBusInterface}
        @param interfaceObj: The interface object containing the method to be
                             invoked

        @type methodName: C{string}
        @param methodName: Name of the method to invoke

        @type methodArguments: C{list}
        @param methodArguments: List of method arguments

        @type sender: C{string}
        @param sender: Unique bus name of the connection invoking the method
        
        @returns: The method return values or a Deferred to the return values
        """

    def getAllProperties(self, interfaceName):
        """
        @type interfaceName: C{string}
        @param interfaceName: The interface to obtain properties from
        
        @returns: a dictionary of DBus property names and their associated values.
                  The values must be marshallable as variants. Consequently, the
                  type-specific wrapper classes within the marshal module may be
                  necessary to ensure the correct encoding type
        """


class _IfaceCache(object):
    def __init__(self, interfaceName):
        self.name       = interfaceName
        self.methods    = dict()
        self.properties = dict()


@implementer(IDBusObject)
class DBusObject (object):
    """
    Straight-forward L{IDBusObject} implementation. This
    implementation provides an API similar to that of
    L{twisted.spread.pb.Referenceable}. Classes to be exported over
    DBus may simply derive from L{DBusObject}, specify their object path
    and supported DBus interfaces in the constructor, and implement
    methods named 'dbus_<methodName>' for each method they wish to
    support.

    @ivar dbusInterfaces: List of L{interface.DBusInterface} objects this class
                          supports. If one or more superclasses also define
                          dbusInterfaces, the contents of those lists will be
                          added to the total interfaces the object supports.
    """
    

    _objectHandler = None

    dbusInterfaces = [ interface.DBusInterface( 'org.freedesktop.DBus.Properties',
                                                 interface.Method('Get', 'ss', 'v'),
                                                 interface.Method('Set', 'ssv'),
                                                 interface.Method('GetAll', 's', 'a{sv}'),
                                                 interface.Signal('PropertiesChanged', 'sa{sv}as') ),
                       ]
    
    def __init__(self, objectPath):
        """
        @type objectPath: C{string}
        @param objectPath: The DBus path of the object. The format of the path
                           must comply with the DBus specification.
        """
        
        self._objectPath    = objectPath
        self._objectHandler = None

        marshal.validateObjectPath(objectPath)


    def _iterIFaceCaches(self):
        
        for base in self.__class__.__mro__:
            
            if base is object:
                return

            cache = base.__dict__.get( '_dbusIfaceCache', None )

            if cache is None:
            
                cache = dict()

                for name, obj in base.__dict__.iteritems():
                    self._cacheInterfaces( base, cache, name, obj )

                setattr(base, '_dbusIfaceCache', cache)

            yield cache
                

    def _cacheInterfaces(self, cls, cache, cls_attr_name, obj):

        def get_ic( interface_name ):
            if not interface_name in cache:
                cache[ interface_name ] = _IfaceCache( interface_name )
            return cache[ interface_name ]
        
        if inspect.isfunction(obj) and hasattr(obj, '_dbusInterface'):
            get_ic( obj._dbusInterface ).methods[ obj._dbusMethod ] = getattr(cls, obj.func_name)

        elif isinstance(obj, DBusProperty):

            if obj.interface is None:
                for iface in self.getInterfaces():
                    if obj.pname in iface.properties:
                        obj.interface = iface.name
                        break

            if obj.interface is None:
                raise AttributeError('No supported DBus interfaces contain a property named "%s"' % obj.pname)

            for iface in self.getInterfaces():
                if obj.interface == iface.name:
                    obj.iprop     = iface.properties[ obj.pname ]
                    break

            get_ic( obj.interface ).properties[ obj.pname ] = obj
            obj.attr_name = cls_attr_name


    def _searchCache(self, interfaceName, cacheAttr, key):
        for cache in self._iterIFaceCaches():
            if interfaceName:
                if interfaceName in cache:
                    d = getattr(cache[interfaceName], cacheAttr)
                    if key in d:
                        return d[ key ]
            else:
                for ic in cache.itervalues():
                    d = getattr(ic, cacheAttr)
                    if key in d:
                        return d[ key ]

                    
    def _getDecoratedMethod(self, interfaceName, methodName):
        f = self._searchCache( interfaceName, 'methods', methodName )
        if f:
            return getattr(self, f.func_name)
                

        
    def _getProperty(self, interfaceName, propertyName):
        return self._searchCache( interfaceName, 'properties', propertyName )
        
            

    def getConnection(self):
        if self._objectHandler:
            return self._objectHandler.conn

    
    def getInterfaces(self):
        for base in self.__class__.__mro__:
            if 'dbusInterfaces' in base.__dict__:
                for iface in base.dbusInterfaces:
                    yield iface

    
    def getObjectPath(self):
        return self._objectPath

    
    def setObjectHandler(self, objectHandler):
        self._objectHandler = objectHandler

    
    def _set_method_flags(self, method_obj):
        """
        Sets the \"_dbusCaller\" boolean on the \"dbus_*\" methods. This
        is a one-time operation used to flag each method with a boolean
        indicating whether or not they accept the \"dbusCaller\" keyword
        argument
        """
        args         = inspect.getargspec(method_obj)[0]
        needs_caller = False

        if len(args) >= 1 and args[-1] == 'dbusCaller':
            needs_caller = True

        method_obj.im_func._dbusCaller = needs_caller
        
        
    def executeMethod(self, interfaceObj, methodName, methodArguments, sender):
        m = getattr(self, 'dbus_' + methodName, None)

        iname = interfaceObj.name
        
        if m is None:
            m = self._getDecoratedMethod( iname, methodName )
            if m is None:
                raise NotImplementedError

        if hasattr(m, '_dbusInterface') and m._dbusInterface != iname:
            m = self._getDecoratedMethod( iname, methodName )
            if m is None:
                raise NotImplementedError
        
        if not hasattr(m, '_dbusCaller'):
            self._set_method_flags(m)
        
        if m._dbusCaller:
            if methodArguments:
                return m( *methodArguments, dbusCaller = sender )
            else:
                return m( dbusCaller = sender )
        else:
            if methodArguments:
                return m( *methodArguments )
            else:
                return m()


    def emitSignal(self, signalName, *args, **kwargs):
        """
        Emits the specified signal with the supplied arguments

        @type signalName: C{string}
        @param signalName: Name of the signal to emit. This must match the
                           name of a signal in one of the objects supported
                           interfaces.

        @type interface: C{string}
        @keyword interface: Optional keyword argument specifying the DBus interface
                            to use. This is only needed if more than one interface
                            defines a signal with the same name.

        @param args: Positional arguments for the signal content
        """
        if self._objectHandler is None:
            return
        
        iface   = kwargs.get('interface',   None)
        
        s = None
        for i in self.getInterfaces():
            if iface and not iface == i.name:
                continue
            
            t = i.signals.get(signalName, None)
            
            if isinstance(t, interface.Signal):
                s = t
                break
            
        if s is None:
            raise AttributeError('Signal "%s" not found in any supported interface.' %
                                 (signalName,))

        msig = message.SignalMessage( self._objectPath, signalName, i.name,
                                           signature = s.sig,
                                           body = args )

        self._objectHandler.conn.sendMessage( msig )



    def getAllProperties(self, interfaceName):
        r = dict()
        
        def addp( p ):
            if p.iprop.access != 'write':
                v = getattr(self, p.attr_name)
                if p.iprop.sig in marshal.variantClassMap:
                    v = marshal.variantClassMap[ p.iprop.sig ]( v )
                r[ p.pname ] = v
                
        if interfaceName:
            for cache in self._iterIFaceCaches():
                ifc = cache.get( interfaceName, None )

                if ifc:
                    for p in ifc.properties.itervalues():
                        addp( p )
                    break

        else:
            for cache in self._iterIFaceCaches():
                for ifc in cache.itervalues():
                    for p in ifc.properties.itervalues():
                        addp( p )

        return r
    

    @dbusMethod('org.freedesktop.DBus.Properties', 'Get')
    def _dbus_PropertyGet(self, interfaceName, propertyName):
        p = self._getProperty(interfaceName, propertyName)
        if p is None:
            raise Exception('Invalid Property')
        
        if p.iprop.access == 'write':
            raise Exception('Property is not readable')
            
        v = getattr(self, p.attr_name)

        if p.iprop.sig in marshal.variantClassMap:
            return marshal.variantClassMap[ p.iprop.sig ]( v )
        else:
            return v


    @dbusMethod('org.freedesktop.DBus.Properties', 'Set')
    def _dbus_PropertySet(self, interfaceName, propertyName, value):
        p = self._getProperty(interfaceName, propertyName)
        
        if p is None:
            raise Exception('Invalid Property')
        
        if p.iprop.access not in ('write', 'readwrite'):
            raise Exception('Property is not Writeable')

        return setattr(self, p.attr_name, value)

        
    @dbusMethod('org.freedesktop.DBus.Properties', 'GetAll')
    def _dbus_PropertyGetAll(self, interfaceName):
        return self.getAllProperties(interfaceName)
                                           

        
class DBusObjectHandler (object):
    """
    This class manages remote and local DBus objects associated with a DBus
    connection. Remote DBus objects are represented by instances of
    RemoteDBusObject.  Local objects exported over DBus must implement the
    IDBusObject interface.
    """
    def __init__(self, connection):
        """
        @type connection: L{client.DBusClientConnection} or L{bus.Bus}
        @param connection: The connection to manage objects for
        """
        self.conn          = connection
        self.exports       = dict() # map object paths => obj
        self._weakProxies  = weakref.WeakValueDictionary()

    
                    
    def connectionLost(self, reason):
        """
        Called by the DBus Connection object when the connection is lost.

        @type reason: L{twistd.python.failure.Failure}
        @param reason: The value passed to the associated connection's
                       connectionLost method.
        """
        for wref in self._weakProxies.valuerefs():
            p = wref()
            if p is not None:
                p.connectionLost(reason)
                


    def exportObject(self, dbusObject):
        """
        Makes the specified object available over DBus
        
        @type dbusObject: an object implementing the L{IDBusObject} interface
        @param dbusObject: The object to export over DBus
        """
        o = IDBusObject( dbusObject )
        self.exports[ o.getObjectPath() ] = o
        o.setObjectHandler(self)

        i = dict()
        for iface in o.getInterfaces():
            i[ iface.name ] = o.getAllProperties( iface.name )


        msig = message.SignalMessage( o.getObjectPath(),
                                      'InterfacesAdded',
                                      'org.freedesktop.DBus.ObjectManager',
                                      signature = 'sa{sa{sv}}',
                                      body = [o.getObjectPath(),
                                              i])

        self.conn.sendMessage( msig )


    def unexportObject(self, objectPath):
        """
        @type objectPath: C{string}
        @param objectPath: Object to stop exporting
        """
        
        o = self.exports[ objectPath ]
        del self.exports[ objectPath ]

        i = [ iface.name for iface in o.getInterfaces() ]


        msig = message.SignalMessage( o.getObjectPath(),
                                      'InterfacesRemoved',
                                      'org.freedesktop.DBus.ObjectManager',
                                      signature = 'sas',
                                      body = [o.getObjectPath(),
                                              i])

        self.conn.sendMessage( msig )


    def getManagedObjects(self, objectPath):
        """
        Returns a Python dictionary containing the reply content for
        org.freedesktop.DBus.ObjectManager.GetManagedObjects
        """
        d = dict()

        for p in sorted(self.exports.keys()):
            if not p.startswith(objectPath) or p == objectPath:
                continue
            o = self.exports[p]
            i = dict()
            d[ p ] = i
            for iface in o.getInterfaces():
                i[ iface.name ] = o.getAllProperties( iface.name )
                
        return d
       


    def _send_err(self, msg, errName, errMsg):
        """
        Helper method for sending error messages
        """
        r = message.ErrorMessage( errName, msg.serial,
                                  body        = [errMsg],
                                  signature   = 's',
                                  destination = msg.sender )

        self.conn.sendMessage( r )


    def handleMethodCallMessage(self, msg):
        """
        Handles DBus MethodCall messages on behalf of the DBus Connection and
        dispatches them to the appropriate exported object
        """
        if msg.interface == 'org.freedesktop.DBus.Peer' and msg.member == 'Ping':
            
            r = message.MethodReturnMessage( msg.serial,
                                             destination = msg.sender )

            self.conn.sendMessage( r )
            return
        
        #Try to get object from complete object path
        o = self.exports.get(msg.path, None)

        if msg.interface == 'org.freedesktop.DBus.Introspectable' and (
            msg.member == 'Introspect'):
            
            xml = None
            
            if o is not None:
                #We have an object, so extract full introspection XML from it
                xml = introspection.generateIntrospectionXML( o.getObjectPath(),
                                                              o.getInterfaces() )
            else:
                #We have no object, perhaps this is a partial path
                xml = introspection.generateIntrospectionXMLForPartialPath( msg.path, 
                                                                            self.exports.keys())
            
            if xml is not None:    
                r = message.MethodReturnMessage( msg.serial,
                                                 body        = [ xml ],
                                                 destination = msg.sender,
                                                 signature   = 's' )
                    
                self.conn.sendMessage( r )
                
                return

        if o is None:
            self._send_err( msg, 'org.freedesktop.DBus.Error.UnknownObject',
                            '%s is not an object provided by this process.' %
                            (msg.path))
            return

        if msg.interface == 'org.freedesktop.DBus.ObjectManager' and (
            msg.member == 'GetManagedObjects'):

            i_and_p = self.getManagedObjects( o.getObjectPath() )

            r = message.MethodReturnMessage( msg.serial,
                                             body        = [ i_and_p ],
                                             destination = msg.sender,
                                             signature   = 'a{oa{sa{sv}}}' )
                
            self.conn.sendMessage( r )
            
            return
        

        i = None
        
        for x in o.getInterfaces():
            if msg.interface:
                if x.name == msg.interface:
                    i = x
                    break
            else:
                if msg.member in x.methods:
                    i = x
                    break

        m = None
        if i:
            m = i.methods.get( msg.member, None )

        if m is None:
            self._send_err( msg, 'org.freedesktop.DBus.Error.UnknownMethod',
                            'Method "%s" with signature "%s" on interface "%s" doesn\'t exist' %
                            (msg.member, msg.signature or '',
                             msg.interface or '(null)'))
            return

        msig = msg.signature if msg.signature is not None else ''
        esig = m.sigIn       if m.sigIn       is not None else ''
            
        if esig != msig:
            self._send_err( msg, 'org.freedesktop.DBus.Error.InvalidArgs',
                            'Call to %s has wrong args (%s, expected %s)' %
                            (msg.member, msg.signature or '', m.sigIn or ''))
            return

        d = defer.maybeDeferred(o.executeMethod,
                                i,
                                msg.member,
                                msg.body,
                                msg.sender)
        
        if msg.expectReply:
            def send_reply( return_values ):                
                if isinstance( return_values, (list, tuple)):
                    if m.nret == 1:
                        return_values = [return_values]
                else:
                    return_values = [return_values]
                
                r = message.MethodReturnMessage( msg.serial,
                                                      body        = return_values,
                                                      destination = msg.sender,
                                                      signature   = m.sigOut )
                self.conn.sendMessage( r )

            def send_error( err ):
                e = err.value
                errMsg = err.getErrorMessage()
                name    = None
                
                if hasattr(e, 'dbusErrorName'):
                    name = e.dbusErrorName

                if name is None:
                    name = 'org.txdbus.PythonException.' + e.__class__.__name__

                try:
                    marshal.validateErrorName( name )
                except error.MarshallingError as e:
                    errMsg = ('!!(Invalid error name "%s")!! ' % name) + errMsg
                    name   = 'org.txdbus.InvalidErrorName'

                r = message.ErrorMessage( name, msg.serial,
                                               body        = [errMsg],
                                               signature   = 's',
                                               destination = msg.sender )
                self.conn.sendMessage( r )

            d.addCallback( send_reply )
            d.addErrback(send_error)
        

    def getRemoteObject(self, busName, objectPath, interfaces = None,
                        replaceKnownInterfaces = False):
        """
        Creates a L{RemoteDBusObject} instance to represent the
        specified DBus object.  If explicit interfaces are not
        supplied, DBus object introspection will be used to obtain
        them automatically.

        @type busName: C{string}
        @param busName: Name of the bus exporting the desired object

        @type objectPath: C{string}
        @param objectPath: DBus path of the desired object

        @type interfaces: None, C{string} or L{interface.DBusInterface} or a
                          list of C{string}/L{interface.DBusInterface}
        @param interfaces: May be None, a single value, or a list of string
                           interface names and/or instances of
                           L{interface.DBusInterface}. If None or any of the
                           specified interface names are unknown, full
                           introspection will be attempted.  If interfaces
                           consists of solely of L{interface.DBusInterface}
                           instances and/or known interfacep names, no
                           introspection will be preformed.

        @type replaceKnownInterfaces: C{bool}
        @param replaceKnownInterfaces: If True (defaults to False), any
                                       interfaces discovered during the
                                       introspection process will override any
                                       previous, cached values.

        @rtype: L{twisted.internet.defer.Deferred}
        @returns: A Deferred to the L{RemoteDBusObject} instance
        """

        weak_id = (busName, objectPath, interfaces)

        need_introspection  = False
        required_interfaces = set()
        
        if interfaces is not None:

            ifl = list()
            
            if not isinstance(interfaces, list):
                interfaces = [interfaces]
                    
            for i in interfaces:
                if isinstance(i, interface.DBusInterface ):
                    ifl.append(i)
                    required_interfaces.add(i.name)
                else:
                    required_interfaces.add(i)
                    if i in interface.DBusInterface.knownInterfaces:
                        ifl.append( interface.DBusInterface.knownInterfaces[i] )
                    else:
                        need_introspection = True
                        
            if not need_introspection:
                return defer.succeed( RemoteDBusObject( self, busName, objectPath, ifl ) )

        d = self.conn.introspectRemoteObject( busName,
                                              objectPath,
                                              replaceKnownInterfaces )

        def ok( ifaces ):
            
            missing = required_interfaces - set( [ q.name for q in ifaces ] )
            
            if missing:
                raise error.IntrospectionFailed('Introspection failed to find interfaces: ' +
                                                     ','.join(missing))

            prox = RemoteDBusObject( self, busName, objectPath, ifaces )

            self._weakProxies[ weak_id ] = prox
            
            return prox
            

        d.addCallback( ok )

        return d
