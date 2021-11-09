"""
Provides support for DBus introspection

@author: Tom Cocagne
"""
import xml.sax
import xml.sax.handler

from six.moves import cStringIO

from txdbus import interface


_dtd_decl = '''<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">'''  # noqa:
# Line length is acceptable here ^

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


def generateIntrospectionXML(objectPath, exportedObjects):
    """
    Generates the introspection XML for an object path or partial object path
    that matches exported objects.

    This allows for browsing the exported objects with tools such as d-feet.

    @rtype: C{string}
    """
    l = [_dtd_decl]
    l.append('<node name="{}">'.format(objectPath))

    obj = exportedObjects.get(objectPath, None)
    if obj is not None:
        for i in obj.getInterfaces():
            l.append(i.introspectionXml)
        l.append(_intro)

    # make sure objectPath ends with '/' to only get partial matches based on
    # the full path, not a part of a subpath
    if not objectPath.endswith('/'):
        objectPath += '/'
    matches = []
    for path in exportedObjects.keys():
        if path.startswith(objectPath):
            path = path[len(objectPath):].partition('/')[0]
            if path not in matches:
                matches.append(path)

    if obj is None and not matches:
        return None

    for m in matches:
        l.append('<node name="%s"/>' % m)

    l.append('</node>')
    return '\n'.join(l)

# Returns a list of interfaces


def getInterfacesFromXML(xmlStr, replaceKnownInterfaces=False):
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
    handler = IntrospectionHandler(replaceKnownInterfaces)

    xmlStr = xmlStr.strip()
    if xmlStr.startswith('<!DOCTYPE'):
        xmlStr = xmlStr[xmlStr.find('>') + 1:]

    # xml.sax.parseString( xmlStr, handler )
    p = xml.sax.make_parser()
    p.setFeature(xml.sax.handler.feature_validation, False)
    p.setFeature(xml.sax.handler.feature_external_ges, False)
    p.setContentHandler(handler)
    p.parse(cStringIO(xmlStr))

    return handler.interfaces


class IntrospectionHandler(xml.sax.handler.ContentHandler):
    """
    XML Interface description handler
    """

    def __init__(self, replaceKnownInterfaces=False):
        xml.sax.handler.ContentHandler.__init__(self)

        self.skipKnown = not replaceKnownInterfaces

        self.interfaces = []
        self.member = None
        self.isMethod = None
        self.iface = None
        self.skip = False

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
        pass  # ignore for now

    def start_interface(self, attrs):
        iname = str(attrs['name'])

        if iname in interface.DBusInterface.knownInterfaces and self.skipKnown:
            self.skip = True
            self.interfaces.append(
                interface.DBusInterface.knownInterfaces[iname]
            )
        else:
            self.iface = interface.DBusInterface(iname)
            self.interfaces.append(self.iface)

    def end_interface(self):
        self.skip = False

    def start_method(self, attrs):
        self.member = interface.Method(str(attrs['name']))
        self.member.nargs = 0
        self.member.nret = 0
        self.isMethod = True

    def end_method(self):
        self.iface.addMethod(self.member)

    def start_signal(self, attrs):
        self.member = interface.Signal(str(attrs['name']))
        self.member.nargs = 0
        self.isMethod = False

    def end_signal(self):
        self.iface.addSignal(self.member)

    def start_property(self, attrs):
        name = str(attrs['name'])
        sig = str(attrs['type'])
        rw = str(attrs['access'])
        readable = rw.lower() in ('read', 'readwrite')
        writeable = rw.lower() in ('write', 'readwrite')
        self.member = interface.Property(name, sig, readable, writeable)
        self.isMethod = False

    def start_annotation(self, attrs):
        if attrs['name'] == 'org.freedesktop.DBus.Property.EmitsChangedSignal':
            self.member.emits = str(attrs['value']) in ('true', 'invalidates')

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
