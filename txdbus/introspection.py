"""
Provides support for DBus introspection

@author: Tom Cocagne
"""
from six.moves import cStringIO
import xml.sax
import xml.sax.handler

from txdbus import interface


_dtd_decl = '''<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">'''

_intro = '''  <interface name="org.freedesktop.DBus.Introspectable">
    <method name="Introspect">
      <arg direction="out" type="s" />
    </method>
  </interface>
  <interface name="org.freedesktop.DBus.Peer">
    <method name="Ping">
    </method>
  </interface>
  <interface name="org.freedesktop.DBus.ObjectManager">
    <method name="GetManagedObjects">
      <arg direction="out" type="a{oa{sa{sv}}}" />
    </method>
  </interface>'''

def generateIntrospectionXMLForPartialPath( objectPath, objectPathList):
    """
    Generates the introspection XML for a partial object path
    that matches any of the delivered object paths in the list
    
    This method was introduced to make any DBus Service created with txdbus
    behave in a way that d-feet, for example, expects
    
    @rtype: C{string}
    """
    
    # make sure objectPath ends with '/' to only get partial matches based on
    # the full path, not a part of a subpath
    if not objectPath.endswith('/'):
        objectPath += '/'
    
    # collect all objectpaths that match with this partial path
    # and immediately only collect the part of the path after the match
    # and get only the first part of the path that remains (partition)
    matches = [path[len(objectPath):].partition('/')[0] 
               for path in objectPathList 
               if path.startswith(objectPath)]
    if len(matches) == 0:
        return None
    
    l = [_dtd_decl]
    l.append('<node name="%s">' % (objectPath,))
    for m in matches:
        #insert only first part of path
        l.append('<node name="%s"/>' % m )
    l.append('</node>')
    return '\n'.join(l)

def generateIntrospectionXML( objectPath, ifaceList ):
    """
    Generates the introspection XML for an object with the
    supplied list of interfaces

    @rtype: C{string}
    """
    l = [_dtd_decl]
    l.append('<node name="%s">' % (objectPath,))
    for i in ifaceList:
        l.append( i.introspectionXml )
    l.append(_intro)
    l.append('</node>')
    return '\n'.join(l)

# Returns a list of interfaces
def getInterfacesFromXML( xmlStr, replaceKnownInterfaces = False ):
    """
    Parses the supplied Introspection XML string and returns a list of
    L{interface.DBusInerface} instances representing the XML interface
    definitions.

    @type replaceKnownInterfaces: C{bool}
    @param replaceKnownInterfaces: If true, pre-existing interface definitions
                                   will be replaced by the contents of the
                                   interfaces defined within the XML string

    @rtype: C{list} of L{interface.DBusInerface}
    """
    handler = IntrospectionHandler( replaceKnownInterfaces )

    xmlStr = xmlStr.strip()
    if xmlStr.startswith('<!DOCTYPE'):
        xmlStr = xmlStr[ xmlStr.find('>')+1 : ]

    #xml.sax.parseString( xmlStr, handler )
    p = xml.sax.make_parser()
    p.setFeature(xml.sax.handler.feature_validation, False)
    p.setFeature(xml.sax.handler.feature_external_ges, False)
    p.setContentHandler(handler)
    p.parse(cStringIO(xmlStr))

    return handler.interfaces


        
class IntrospectionHandler( xml.sax.handler.ContentHandler ):
    """
    XML Interface description handler
    """

    def __init__(self, replaceKnownInterfaces = False):
        xml.sax.handler.ContentHandler.__init__(self)

        self.skipKnown = not replaceKnownInterfaces
        
        self.interfaces = list()
        self.member     = None
        self.isMethod  = None
        self.iface      = None
        self.skip       = False

        
    def startElement(self, name, attrs):
        if self.skip:
            return
        f = getattr(self, 'start_' + name, None)
        if f:
            f(attrs)

            
    def endElement(self, name):
        if self.skip and name != 'interface':
            return
        
        f = getattr(self, 'end_' + name, None)
        if f:
            f()


    def start_node(self, attrs):
        pass # ignore for now

            
    def start_interface(self, attrs):
        iname = str(attrs['name'])
        
        if iname in interface.DBusInterface.knownInterfaces and self.skipKnown:
            self.skip = True
            self.interfaces.append( interface.DBusInterface.knownInterfaces[iname] )
        else:
            self.iface = interface.DBusInterface( iname )
            self.interfaces.append( self.iface )

            
    def end_interface(self):
        self.skip = False

        
    def start_method(self, attrs):
        self.member       = interface.Method(str(attrs['name']))
        self.member.nargs = 0
        self.member.nret  = 0
        self.isMethod    = True


    def end_method(self):
        self.iface.addMethod( self.member )

        
    def start_signal(self, attrs):
        self.member       = interface.Signal(str(attrs['name']))
        self.member.nargs = 0
        self.isMethod    = False
        

    def end_signal(self):
        self.iface.addSignal(self.member)

        
    def start_property(self, attrs):
        name      = str(attrs['name'])
        sig       = str(attrs['type'])
        rw        = str(attrs['access'])
        readable  = rw.lower() in ('read', 'readwrite')
        writeable = rw.lower() in ('write', 'readwrite')
        self.member   = interface.Property(name, sig, readable, writeable)
        self.isMethod = False

        
    def start_annotation(self, attrs):
        if attrs['name'] == 'org.freedesktop.DBus.Property.EmitsChangedSignal':
            self.member.emits = str(attrs['value']) in ('true','invalidates')

            
    def end_property(self):
        self.iface.addProperty(self.member)

        
    def start_arg(self, attrs):
        t = str(attrs['type'])
        
        if self.isMethod:

            if attrs['direction'] == 'in':
                self.member.nargs += 1
                self.member.sigIn = self.member.sigIn + t
            else:
                self.member.nret += 1
                self.member.sigOut = self.member.sigOut + t
                
        else:
            self.member.nargs += 1
            self.member.sig = self.member.sig + t
