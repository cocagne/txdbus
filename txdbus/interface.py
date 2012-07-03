"""
This module contains classes implementing the DBus definition of
interfaces. These are distinct from the Zope/Twisted component
model's definition of Interfaces.

@author: Tom Cocagne
"""

from txdbus import marshal


class Method (object):
    """
    Represents a Method declaration in a DBus Interface.

    @type name: C{string}
    @param name: Method name. This must be a valid DBus interface name

    @type arguments: C{string}
    @param arguments: DBus signature for method arguments this must be either
                      an empty string, indicating no arguments, or a valid
                      signature string as defined by the DBus specification.

    @type returns: C{string}
    @param returns: DBus signature for method return values this must be either
                    an empty string, indicating no arguments, or a valid
                    signature string as defined by the DBus specification.
    """
    __slots__ = ['name', 'nargs', 'nret', 'sigIn', 'sigOut']
    def __init__(self, name, arguments='', returns='' ):
        self.name    = name
        self.nargs   = -1
        self.nret    = -1
        self.sigIn  = arguments
        self.sigOut = returns

        
class Signal (object):
    """
    Represents a Signal declaration in a DBus Interface

    @type name: C{string}
    @param name: Signal name. This must be a valid DBus interface name

    @type arguments: C{string}
    @param arguments: DBus signature for signal arguments this must be either
                      an empty string, indicating no arguments, or a valid
                      signature string as defined by the DBus specification.
    """
    __slots__ = ['name', 'nargs', 'sig']
    def __init__(self, name, arguments=''):
        self.name    = name
        self.nargs   = -1
        self.sig     = arguments



class Property (object):
    """
    Represents a Property declaration in a DBus Interface.

    @type name: C{string}
    @param name: Property name. This must be a valid DBus interface name

    @type sig: C{string}
    @param sig: DBus signature for the property data type

    @type readable: C{bool}
    @param readable: True if the property is readable (defaults to True)

    @type writeable: C{bool}
    @param writeable: True if the property is writeable (defaults to False)

    @type emitsOnChange: C{bool}
    @param emitsOnChange: True if changes to the property result in a
    org.freedesktop.DBus.Properties.PropertiesChanged signal being emitted (defaults to True)
    """
    __slots__ = ['name', 'sig', 'access', 'emits']
    def __init__(self, name, sig, readable=True, writeable=False, emitsOnChange=True):
        self.name   = name
        self.sig    = sig

        if writeable and not readable:
            self.access = 'write'

        elif writeable and readable:
            self.access = 'readwrite'

        else:
            self.access = 'read'

        if not emitsOnChange in (True, False, 'invalidates'):
            raise TypeError('emitsOnChange parameter must be one of True, False, or "invalidates"')

        if type(emitsOnChange) is bool:
            self.emits = 'true' if emitsOnChange else 'false'
        else:
            self.emits  = emitsOnChange
            

    
class DBusInterface (object):
    """
    Represents a DBus Interface Definition. The introspectionXml property
    contains the full XML introspection description of the interface defined by
    an instance of this class.

    @type knownInterfaces: C{dict}
    @cvar knownInterfaces: Dictionary cache of interface name to
                           L{DBusInterface} objects. This cache is used to
                           avoid continual interface re-instrospection

    @type introspectionXml: C{string}
    @ivar introspectionXml: XML string containing the interface definition
    """
    
    knownInterfaces = dict()
    
    def __init__(self, name, *args, **kwargs):
        """
        Method and fSignal instances to be included in the interface may be
        passed as additional positional parameters after 'name'.

        @keyword noRegister: If passed as a keyword argument this prevents the interface
                             definition from being cached for future use
        """
        self.name       = name
        self.methods    = dict()
        self.signals    = dict()
        self.properties = dict()
        self._xml       = None

        for x in args:
            if isinstance(x, Method):
                self.addMethod(x)
            elif isinstance(x, Signal):
                self.addSignal(x)
            elif isinstance(x, Property):
                self.addProperty(x)
            else:
                raise TypeError('Invalid interface argument: %s' % (repr(x),))

        if not 'noRegister' in kwargs:
            self.knownInterfaces[ name ] = self
        

    def addMethod(self, m):
        """
        Adds a L{Method} to the interface
        """
        if m.nargs == -1:
            m.nargs = len( [ a for a in marshal.genCompleteTypes( m.sigIn ) ] )
            m.nret  = len( [ a for a in marshal.genCompleteTypes( m.sigOut ) ] )
        self.methods[ m.name ] = m
        self._xml = None

        
    def addSignal(self, s):
        """
        Adds a L{Signal} to the interface
        """
        if s.nargs == -1:
            s.nargs = len( [ a for a in marshal.genCompleteTypes( s.sig ) ] )
        self.signals[ s.name ] = s
        self._xml = None

        
    def addProperty(self, p):
        self.properties[ p.name ] = p
        self._xml = None

        
    def delMethod(self, name):
        """
        Deletes the named method
        """
        del self.methods[name]
        self._xml = None

        
    def delSignal(self, name):
        """
        Deletes the named signal
        """
        del self.signals[ name ]
        self._xml = None

        
    def delProperty(self, name):
        """
        Deletes the named property
        """
        del self.properties[ name ]
        self._xml = None


    def _getXml(self):
#        """
#        @returns: an XML description of the interface
#        @rtype: C{string}
#        """
        if self._xml is None:
            l = list()
            l.append('  <interface name="%s">' % (self.name,))

            k = self.methods.keys()
            k.sort()
            for m in ( self.methods[a] for a in k ):
                l.append('    <method name="%s">' % (m.name,))
                for arg_sig in marshal.genCompleteTypes( m.sigIn ):
                    l.append('      <arg direction="in" type="%s"/>' % (arg_sig,))
                for arg_sig in marshal.genCompleteTypes( m.sigOut ):
                    l.append('      <arg direction="out" type="%s"/>' % (arg_sig,))
                l.append('    </method>')

            k = self.signals.keys()
            k.sort()
            for s in ( self.signals[a] for a in k ):
                l.append('    <signal name="%s">' % (s.name,))
                for arg_sig in marshal.genCompleteTypes( s.sig ):
                    l.append('      <arg type="%s"/>' % (arg_sig,))
                l.append('    </signal>')

            k = self.properties.keys()
            k.sort()
            for p in ( self.properties[a] for a in k ):
                l.append('    <property name="%s" type="%s" access="%s">' % (p.name, p.sig, p.access,))
                l.append('      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="%s"/>' % (p.emits,))
                l.append('    </property>')

            l.append('  </interface>')

            self._xml = '\n'.join(l)
        return self._xml

    introspectionXml = property(_getXml)

    #def printSelf(self):
    #    """
    #    Debugging utility that prints the interface to standard output
    #    """
    #    print 'Interface: ', self.name
    #    def sdict(d):
    #        l = d.keys()
    #        l.sort()
    #        return [ d[x] for x in l ]
    #    for m in sdict(self.methods):
    #        print '    Method:', m.name, ' in =', m.sigIn, ' out =', m.sigOut
    #
    #    for s in sdict(self.signals):
    #        print '    Signals:', s.name, ' sig =', s.sig
