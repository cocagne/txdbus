"""
Endpoint creation from DBus address strings

@author: Tom Cocagne
"""
import os

from twisted.internet.endpoints import UNIXClientEndpoint, TCP4ClientEndpoint
from twisted.internet.endpoints import UNIXServerEndpoint, TCP4ServerEndpoint



def getDBusEnvEndpoints(reactor, client = True):
    """
    Creates endpoints from the DBUS_SESSION_BUS_ADDRESS environment variable
    
    @rtype: C{list} of L{twisted.internet.interfaces.IStreamServerEndpoint}
    @returns: A list of endpoint instances
    """
    env = os.environ.get('DBUS_SESSION_BUS_ADDRESS', None)
    if env is None:
        raise Exception('DBus Session environment variable not set')

    return getDBusEndpoints( reactor, env, client )



def getDBusEndpoints(reactor, busAddress, client=True):
    """
    Creates DBus endpoints.

    @param busAddress: 'session', 'system', or a valid bus address as defined by
                       the DBus specification. If 'session' (the default) or 'system'
                       is supplied, the contents of the DBUS_SESSION_BUS_ADDRESS or
                       DBUS_SYSTEM_BUS_ADDRESS environment variables will be used for
                       the bus address, respectively. If DBUS_SYSTEM_BUS_ADDRESS is not
                       set, the well-known address unix:path=/var/run/dbus/system_bus_socket
                       will be used.
    @type busAddress: C{string}
    
    @rtype: C{list} of L{twisted.internet.interfaces.IStreamServerEndpoint}
    @returns: A list of endpoint instances
    """

    if busAddress == 'session':
        addrString = os.environ.get('DBUS_SESSION_BUS_ADDRESS', None)
        if addrString is None:
            raise Exception('DBus Session environment variable not set')

    elif busAddress == 'system':
        addrString = os.environ.get('DBUS_SYSTEM_BUS_ADDRESS',
                                    'unix:path=/var/run/dbus/system_bus_socket')

    else:
        addrString = busAddress
    
    #XXX Add documentation about extra key=value parameters in address string
    #    such as nonce-tcp vs tcp which use same endpoint class
    epl = list()

    for ep_addr in addrString.split(';'):
        d    = dict()
        kind = None
        ep   = None
        
        for c in ep_addr.split(','):
            if c.startswith('unix:'):
                kind = 'unix'
                c = c[5:]
            elif c.startswith('tcp:'):
                kind = 'tcp'
                c = c[4:]
            elif c.startswith('nonce-tcp:'):
                kind = 'tcp'
                c = c[10:]
                d['nonce-tcp'] = True
            elif c.startswith('launchd:'):
                kind = 'launchd'
                c = c[7:]

            if '=' in c:
                k,v = c.split('=')
                d[k] = v

        if kind == 'unix':
            if 'path' in d:
                path = d['path']
            elif 'tmpdir' in d:
                path = d['tmpdir'] + '/dbus-' + str(os.getpid())
            elif 'abstract' in d:
                path = '\0' + d['abstract']

            if client:
                ep = UNIXClientEndpoint(reactor, path=path)
            else:
                ep = UNIXServerEndpoint(reactor, address=path)

        elif kind == 'tcp':
            if client:
                ep = TCP4ClientEndpoint(reactor, d['host'], int(d['port']))
            else:
                ep = TCP4ServerEndpoint(reactor, int(d['port']), interface=d['host'])

        if ep:
            ep.dbus_args = d
            epl.append(ep)

    return epl

        

