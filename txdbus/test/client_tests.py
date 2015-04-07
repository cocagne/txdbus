#
# This module is structured somewhat unusually in order to allow the
# code to be shared between two different modules that run these
# tests against the internally implemented bus and the OS native
# bus if it's available
#
# Those modules dynamically create subclasses of all classes
# deriving from ServerObjectTester, unittest.TestClass, and
# an optional mixin class for setting up the internal bus.
#

from __future__ import print_function

import os

from twisted.internet import reactor, defer

from txdbus import objects, endpoints, bus, error, client, introspection
from txdbus.interface import DBusInterface, Method, Signal, Property

from txdbus.objects import dbusMethod, DBusProperty



def delay(arg):
    d = defer.Deferred()
    reactor.callLater(0.05, lambda : d.callback(arg) )
    return d

class TestException (Exception):
    dbusErrorName = 'org.txdbus.trial.TestException'




class ServerObjectTester(object):
    tst_path  = '/TestObj'
    tst_bus   = 'org.txdbus.trial.bus%d' % os.getpid()
    TestClass = None
    

    @defer.inlineCallbacks
    def setUp(self):
        yield self._setup()
        yield self._client_connect()
        

    def _client_connect(self):
        self.t           = self.TestClass(self.tst_path)
        self.server_conn = None
        self.client_conn = None
            
        f = client.DBusClientFactory()

        point = endpoints.getDBusEnvEndpoints(reactor)[0]
        point.connect(f)
        
        d = f.getConnection()
        d.addCallback(self._connected)
        d.addCallback( lambda _: self.get_client_connection() )

        return d
        

    def _connected(self, conn):
        self.server_conn = conn
        conn.exportObject(self.t)
        return conn.requestBusName(self.tst_bus)

    
    def tearDown(self):        
        if self.client_conn:
            self.client_conn.disconnect()

        if self.server_conn:
            self.server_conn.disconnect()

        return self._teardown()


    def get_client_connection(self):
        if self.client_conn:
            return defer.succeed(self.client_conn)
        else:
            f = client.DBusClientFactory()

            point = endpoints.getDBusEnvEndpoints(reactor)[0]
            point.connect(f)

            d = f.getConnection()

            def got_connection(c):
                self.client_conn = c
                return c
            

            d.addCallback(got_connection)
            
            return d

        
    def get_proxy(self, interfaces=None):
        d = self.get_client_connection()

        def gotit(conn):
            return conn.getRemoteObject( self.tst_bus, self.tst_path, interfaces=interfaces )

        d.addCallback(gotit)
        return d

    
    def proxy_chain(self, *args):
        d = self.get_proxy()

        for a in args:
            d.addCallback(a)

        return d



class SimpleObjectTester(ServerObjectTester):
    class TestClass (objects.DBusObject):

        tif = DBusInterface( 'org.txdbus.trial.Simple',
                             Method('testMethod', arguments='s', returns='s' ),
                             Signal('tsig', 's')
                             )

        dbusInterfaces = [tif]

        def __init__(self, object_path):
            objects.DBusObject.__init__(self, object_path)


        def dbus_testMethod(self, arg):
            return arg + 'bar'

        

class ConnectionTest(SimpleObjectTester):
    
    def test_client_connect(self):
        d = client.connect(reactor)

        def ok(conn):
            conn.disconnect()
            self.assertTrue(True)
            
        d.addCallback( ok )

        return d

    def test_fallback_connect(self):
        bad1 = 'unix:abstract=/tmp/FOOBARBAZBLICK,guid=5'
        bad2 = 'tcp:host=127.0.0.99,port=0,family="ipv4",guid=5'
        good = os.environ['DBUS_SESSION_BUS_ADDRESS']

        d = client.connect(reactor, '%s;%s;%s' % (bad1,bad2,good) )

        def ok(conn):
            conn.disconnect()
            self.assertTrue(True)
            
        d.addCallback( ok )

        return d

    def test_failed_connect(self):
        bad1 = 'unix:abstract=/tmp/FOOBARBAZBLICK,guid=5'
        bad2 = 'tcp:host=127.0.0.99,port=0,family="ipv4",guid=5'

        d = client.connect(reactor, '%s;%s' % (bad1,bad2) )

        def ok(conn):
            conn.disconnect()
            self.assertTrue(False, 'Connect should not have succeeded')
            
        d.addCallback( ok )
        d.addErrback( lambda _: self.assertTrue(True) )

        return d

    def test_no_valid_endpoints(self):
        bad1 = 'unix:abstract=/tmp/FOOBARBAZBLICK,guid=5'
        bad2 = 'tcp:host=127.0.0.99,port=0,family="ipv4",guid=5'

        d = client.connect(reactor, '' )

        def ok(conn):
            conn.disconnect()
            self.assertTrue(False, 'Connect should not have succeeded')
            
        d.addCallback( ok )
        d.addErrback( lambda _: self.assertTrue(True) )

        return d

class InheritiedInterfaceTest(SimpleObjectTester):

    class TestClass (SimpleObjectTester.TestClass):

        tif = DBusInterface( 'org.txdbus.trial.SimpleSub',
                             Method('testMethodSub', arguments='s', returns='s' ),
                             Signal('tsig', 's')
                             )

        dbusInterfaces = [tif]

        def __init__(self, object_path):
            objects.DBusObject.__init__(self, object_path)


        def dbus_testMethodSub(self, arg):
            return arg + 'barSub'

    def test_subclass_method(self):

        def got_object(ro):
            return ro.callRemote('testMethodSub', 'foo')

        def got_reply(reply):
            self.assertEquals(reply, 'foobarSub')

        return self.proxy_chain(got_object, got_reply)

    def test_superclass_method(self):

        def got_object(ro):
            return ro.callRemote('testMethod', 'foo')

        def got_reply(reply):
            self.assertEquals(reply, 'foobar')

        return self.proxy_chain(got_object, got_reply)


    
class ObjectManagerTest(SimpleObjectTester):

    class TestClass (SimpleObjectTester.TestClass):

        tif = DBusInterface( 'org.txdbus.trial.SimpleSub',
                             Method('testMethodSub', arguments='s', returns='s' ),
                             Method('foo', returns='s' ),
                             Signal('tsig', 's'),
                             Property('prop', 'i')
                             )

        dbusInterfaces = [tif]

        prop = DBusProperty('prop')

        def __init__(self, object_path, arg=-1):
            objects.DBusObject.__init__(self, object_path)
            self.prop = arg

        def dbus_foo(self):
            return 'foo'

            
    def test_get_managed_objects(self):
        t1 = self.TestClass('/org/test/Foo',     0)
        t2 = self.TestClass('/org/test/Foo/Bar', 1)
        t3 = self.TestClass('/org/test/Foo/Baz', 2)

        self.server_conn.exportObject(t1)
        self.server_conn.exportObject(t2)
        self.server_conn.exportObject(t3)

        def get_proxy( path ):
            d = self.get_client_connection()

            def gotit(conn):
                return conn.getRemoteObject( self.tst_bus, path )

            d.addCallback(gotit)
            return d

        def got_object(ro):
            return ro.callRemote('GetManagedObjects')

        def got_reply(reply):
            self.assertEquals(reply, {
                    '/org/test/Foo/Bar': {
                        'org.freedesktop.DBus.Properties' : {},
                        'org.txdbus.trial.Simple' : {},
                        'org.txdbus.trial.SimpleSub' : {'prop': 1},
                        },
                    '/org/test/Foo/Baz': {
                        'org.freedesktop.DBus.Properties' : {},
                        'org.txdbus.trial.Simple' : {},
                        'org.txdbus.trial.SimpleSub' : {'prop': 2},
                        },
                    })

        dp = get_proxy('/org/test/Foo')

        dp.addCallback(got_object)
        dp.addCallback(got_reply)

        return dp

    @defer.inlineCallbacks
    def test_unexport_objects(self):
        t1 = self.TestClass('/org/test/Foo',     0)
        t2 = self.TestClass('/org/test/Foo/Bar', 1)
        t3 = self.TestClass('/org/test/Foo/Baz', 2)

        self.server_conn.exportObject(t1)
        self.server_conn.exportObject(t2)
        self.server_conn.exportObject(t3)

        conn = yield self.get_client_connection()
        ro1  = yield conn.getRemoteObject(self.tst_bus, '/org/test/Foo')
        ro2  = yield conn.getRemoteObject(self.tst_bus, '/org/test/Foo/Bar')

        f1 = yield ro1.callRemote('foo')
        f2 = yield ro2.callRemote('foo')
        
        self.assertEquals( f1, 'foo' )
        self.assertEquals( f2, 'foo' ) 
                
        self.server_conn.unexportObject('/org/test/Foo')

        f2 = yield ro2.callRemote('foo')
        self.assertEquals( f2, 'foo' ) 

        try:
            f1 = yield ro1.callRemote('foo')
            self.fail('failed throw exception')
        except error.RemoteError as e:
            self.assertEquals(e.message, '/org/test/Foo is not an object provided by this process.')
        except Exception:
            self.fail('Threw wrong exception')
        

        

    def test_interface_added_signal(self):
        dsig = defer.Deferred()
        
        def on_signal( m ):
            dsig.callback(m)

        def check_results(m):
            self.assertEquals(m.interface, 'org.freedesktop.DBus.ObjectManager')
            self.assertEquals(m.member, 'InterfacesAdded')
            self.assertEquals(m.body, [
                    '/org/test/Foo',
                    {
                        'org.txdbus.trial.SimpleSub' : {'prop' : 0},
                        'org.txdbus.trial.Simple' : {},
                        'org.freedesktop.DBus.Properties' : {}
                        }
                    ])
            
        def on_proxy( ro ):
            return self.client_conn.addMatch( on_signal,
                                              mtype     = 'signal',
                                              sender    = self.tst_bus )
        # path_namespace is available in dbus 1.5+
                                              #path_namespace    = '/org/test' )

        def sendit(ro):
            t = self.TestClass('/org/test/Foo',0)
            self.server_conn.exportObject(t)

        d = self.get_proxy()

        d.addCallback(on_proxy)
        d.addCallback(sendit)
        d.addCallback( lambda _: dsig )
        d.addCallback( check_results )

        return d

    def test_interface_removed_signal(self):
        dsig = defer.Deferred()

        t = self.TestClass('/org/test/Foo',0)
        
        def on_signal( m ):
            dsig.callback(m)

        def check_results(m):
            self.assertEquals(m.interface, 'org.freedesktop.DBus.ObjectManager')
            self.assertEquals(m.member, 'InterfacesRemoved')
            self.assertEquals(m.body, [
                    '/org/test/Foo', [
                        'org.txdbus.trial.SimpleSub',
                        'org.txdbus.trial.Simple',
                        'org.freedesktop.DBus.Properties'
                        ]
                    ])
            
        def on_proxy( ro ):
            self.server_conn.exportObject(t)
            
            return self.client_conn.addMatch( on_signal,
                                              mtype     = 'signal',
                                              sender    = self.tst_bus,
                                              member    = 'InterfacesRemoved')
        # path_namespace is available in dbus 1.5+
                                              #path_namespace    = '/org/test' )

        def sendit(ro):
            self.server_conn.unexportObject('/org/test/Foo')

        d = self.get_proxy()

        d.addCallback(on_proxy)
        d.addCallback(sendit)
        d.addCallback( lambda _: dsig )
        d.addCallback( check_results )

        return d


    
    
class SimpleTest(SimpleObjectTester):

    def test_bad_remote_method_call(self):
        d = self.client_conn.callRemote( self.tst_path, '0badmember',
                                         interface   = 'org.freedesktop.DBus.Peer',
                                         destination = self.tst_bus,
                                         body = 1 )
        
        d.addCallback( lambda _: self.assertTrue(False, 'Remote call should have errbacked') )
        d.addErrback( lambda _: self.assertTrue(True) )

        return d

    def test_simple(self):

        def got_object(ro):
            return ro.callRemote('testMethod', 'foo')

        def got_reply(reply):
            self.assertEquals(reply, 'foobar')

        return self.proxy_chain(got_object, got_reply)

    def test_get_connection(self):

        def got_object(ro):
            self.assertTrue( self.t.getConnection() is not None ) 

        return self.proxy_chain(got_object)


    def test_get_name_owner(self):

        d = self.server_conn.getNameOwner(self.tst_bus)

        def got_reply(reply):
            self.assertEquals(reply, self.server_conn.busName)

        d.addCallback(got_reply)

        return d


    def test_manual_interface(self):

        def on_proxy(ro):
            return ro.callRemote('testMethod', 'foo')

        def on_reply(reply):
            self.assertEquals(reply, 'foobar')

        d = self.get_proxy( SimpleObjectTester.TestClass.tif )
        d.addCallback( on_proxy )
        d.addCallback( on_reply )
        return d


    def test_extra_arguments(self):

        def on_proxy(ro):

            return ro.callRemote('testMethod', 'foo',
                                 expectReply = False,
                                 autoStart = False,
                                 timeout = 5 )


        def on_reply(reply):
            self.assertTrue( reply is None )

        def on_error(err):
            print('***** GOT TIMEOUT ******', err.getErrorMessage())
            print('    ', err.value)
            self.assertTrue( isinstance(err.value, error.TimeOut), 'Did not receive a timeout' )

        d = self.get_proxy()
        d.addCallback( on_proxy )
        d.addCallbacks( on_reply, on_error )
        return d

    
    def test_ping(self):

        d = self.client_conn.callRemote( self.tst_path, 'Ping',
                                         interface   = 'org.freedesktop.DBus.Peer',
                                         destination = self.tst_bus )
        d.addCallback( lambda _: self.assertTrue(True) )

        return d

    
    def test_hello_hello(self):

        
        def on_proxy(ro):
            return self.client_conn.callRemote( '/org/freedesktop/DBus', 'Hello',
                                                interface   = 'org.freedesktop.DBus',
                                                destination = 'org.freedesktop.DBus' )

        def on_err( e ):
            self.assertEquals('org.freedesktop.DBus.Error.Failed: Already handled an Hello message',
                              str(e.value))

        d = self.get_proxy()
        d.addCallback( on_proxy )

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )

        return d

    


class DisconnectTest(SimpleObjectTester):

    def test_notify_on_disconnect(self):
        dresult = defer.Deferred()

        def fail():
            dresult.callback(None)
            self.fail('Failed to receive disconnect notification on remote object')

        fail_cb = reactor.callLater(5, fail)
        
        def on_disconnect(robj, reason):
            fail_cb.cancel()
            self.assertTrue(True)
            dresult.callback(None)            

        def on_proxy(ro):
            self.proxy = ro # ensure proxy object doesn't get GC-ed
            ro.notifyOnDisconnect( on_disconnect )
            self.client_conn.disconnect()
            self.client_conn = None

        d = self.get_proxy()
        d.addCallback( on_proxy )

        return dresult


    def test_cancel_notify_on_disconnect(self):
        dresult = defer.Deferred()

        def ok():
            self.assertTrue(True)
            dresult.callback(None)
            
        ok_cb = reactor.callLater(0.1, ok)
        
        def on_disconnect(robj, reason):
            ok_cb.cancel()
            self.fail('Should not have received disconnect notification on remote object')
            dresult.callback(None)            

        def on_proxy(ro):
            self.proxy = ro # ensure proxy object doesn't get GC-ed
            ro.notifyOnDisconnect( on_disconnect )
            ro.cancelNotifyOnDisconnect( on_disconnect )
            self.client_conn.disconnect()
            self.client_conn = None

        d = self.get_proxy()
        d.addCallback( on_proxy )

        return dresult

        

        

            
    

class IntrospectionTest(SimpleObjectTester):

    class TestClass (objects.DBusObject):

        tif = DBusInterface( 'org.txdbus.trial.Simple',
                             Method('testMethod', arguments='s', returns='s' ),
                             Signal('tsig', 's'),
                             Property('foo', 's', emitsOnChange=False),
                             Property('bar', 'i', True, True, True),
                             Property('baz', 's', False, True, 'invalidates')
                             )
        dbusInterfaces = [tif]

        def __init__(self, object_path):
            objects.DBusObject.__init__(self, object_path)

    introspection_golden_xml = """<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node name="/TestObj">
  <interface name="org.txdbus.trial.Simple">
    <method name="testMethod">
      <arg direction="in" type="s"/>
      <arg direction="out" type="s"/>
    </method>
    <signal name="tsig">
      <arg type="s"/>
    </signal>
    <property name="bar" type="i" access="readwrite">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="baz" type="s" access="write">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="invalidates"/>
    </property>
    <property name="foo" type="s" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
    </property>
  </interface>
  <interface name="org.freedesktop.DBus.Properties">
    <method name="Get">
      <arg direction="in" type="s"/>
      <arg direction="in" type="s"/>
      <arg direction="out" type="v"/>
    </method>
    <method name="GetAll">
      <arg direction="in" type="s"/>
      <arg direction="out" type="a{sv}"/>
    </method>
    <method name="Set">
      <arg direction="in" type="s"/>
      <arg direction="in" type="s"/>
      <arg direction="in" type="v"/>
    </method>
    <signal name="PropertiesChanged">
      <arg type="s"/>
      <arg type="a{sv}"/>
      <arg type="as"/>
    </signal>
  </interface>
  <interface name="org.freedesktop.DBus.Introspectable">
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
  </interface>
</node>"""


    def test_introspection(self):
        d = self.get_client_connection()

            
        def cb( c ):
            return c.callRemote(self.tst_path, 'Introspect',
                                interface   = 'org.freedesktop.DBus.Introspectable',
                                destination = self.tst_bus )

        def gotxml( xml ):
            #with open('/tmp/tout', 'w') as f:
            #    f.write(xml)
            self.assertEquals(self.introspection_golden_xml, xml)

        d.addCallback(cb)
        d.addCallback(gotxml)
        return d

    def test_introspection_parsing(self):
        ifaces = introspection.getInterfacesFromXML( self.introspection_golden_xml, True )
        for iface in ifaces:
            if iface.name == 'org.txdbus.trial.Simple':
                break
        else:
            self.assertTrue(False)

        self.assertTrue( 'testMethod' in iface.methods )
        self.assertTrue( 'tsig' in iface.signals )
        self.assertTrue( 'foo' in iface.properties )
        
        



class SignalTester(ServerObjectTester):

    class TestClass (objects.DBusObject):

        tif = DBusInterface( 'org.txdbus.trial.Signal',
                             Method('sendSignal', arguments='s'),
                             Method('sendShared1'),
                             Method('sendEmpty'),
                             Method('sendRaw', arguments='s'),
                             Signal('testSignal', 's'),
                             Signal('sharedSignal', 's'),
                             Signal('emptySig')
                             )
        tif2 = DBusInterface( 'org.txdbus.trial.Signal2',
                             Method('sendShared2'),
                             Signal('sharedSignal', 's')
                             )

        dbusInterfaces = [tif, tif2]

        def __init__(self, object_path):
            objects.DBusObject.__init__(self, object_path)


        def dbus_sendSignal(self, arg):
            self.emitSignal('testSignal', 'Signal arg: ' + arg)

        def dbus_sendRaw(self, arg):
            self.emitSignal('testSignal', arg)

        def dbus_sendEmpty(self):
            self.emitSignal('emptySig')
            
        def dbus_sendShared1(self):
            self.emitSignal('sharedSignal', 'iface1',
                            interface='org.txdbus.trial.Signal')

        def dbus_sendShared2(self):
            self.emitSignal('sharedSignal', 'iface2',
                            interface='org.txdbus.trial.Signal2')


    def test_signal(self):        
        dsig = defer.Deferred()
        
        def on_signal( arg ):
            dsig.callback( arg )
            
        def on_proxy( ro ):
            ro.notifyOnSignal('testSignal', on_signal)
            return ro.callRemote('sendSignal', 'foo')

        d = self.get_proxy()

        d.addCallback(on_proxy)

        def check_result( result ):
            self.assertEquals( result, 'Signal arg: foo' )

        dsig.addCallback(check_result)

        return defer.DeferredList( [d, dsig] )

    def test_signal_no_parameters(self):        
        dsig = defer.Deferred()
        
        def on_signal():
            dsig.callback( None )
            
        def on_proxy( ro ):
            ro.notifyOnSignal('emptySig', on_signal)
            return ro.callRemote('sendEmpty')

        d = self.get_proxy()

        d.addCallback(on_proxy)

        return defer.DeferredList( [d, dsig] )


    def test_bad_signal_interface(self):        
        
        def on_signal( arg ):
            pass
            
        def on_proxy( ro ):
            self.assertRaises(AttributeError, ro.notifyOnSignal, 'testSignal', on_signal, 'foo_iface')
            
        d = self.get_proxy()

        d.addCallback(on_proxy)

        return d


    def test_signal_cancel(self):        
        counts  = dict( signal_count = 0 )
        
        def on_signal(_):
            counts[ 'signal_count' ] += 1
            
        def on_proxy( ro ):
            dnotify = ro.notifyOnSignal('testSignal', on_signal)

            def send_signal( rule_id ):
                dx = ro.callRemote('sendSignal', 'foo')
                dx.addCallback( lambda _: rule_id )
                return dx

            def cancel_reg( rule_id ):
                return ro.cancelSignalNotification( rule_id )

            def delay(arg):
                d = defer.Deferred()
                reactor.callLater(0.1, lambda : d.callback(arg) )
                return d

            def check_result(y):
                self.assertEqual(counts['signal_count'], 1)

            dnotify.addCallback( send_signal )
            dnotify.addCallback( cancel_reg  )
            dnotify.addCallback( send_signal )
            dnotify.addCallback( check_result )

            return dnotify
            

        d = self.get_proxy()

        d.addCallback(on_proxy)
        
        return d

    def test_shared_signal(self):        
        
        d1 = defer.Deferred()
        d2 = defer.Deferred()
        
        def on_proxy( ro ):
            ro.notifyOnSignal('sharedSignal', d1.callback,
                              interface='org.txdbus.trial.Signal')
            ro.notifyOnSignal('sharedSignal', d2.callback,
                              interface='org.txdbus.trial.Signal2')

            ro.callRemote('sendShared1')
            ro.callRemote('sendShared2')


        self.get_proxy().addCallback(on_proxy)


        dl = defer.DeferredList( [d1,d2] )

        def check_result( result ):
            self.assertEquals( result[0], (True, 'iface1') )
            self.assertEquals( result[1], (True, 'iface2') )

        dl.addCallback(check_result)

        return dl


    def test_arg_rule_match(self):
        dsig = defer.Deferred()

        def on_signal( result ):
            dsig.callback( result )
            
        d = self.client_conn.addMatch( on_signal,
                                       mtype     = 'signal',
                                       sender    = self.tst_bus,
                                       arg       = [(0,'Signal arg: MATCH')])
        
        def on_proxy( ro ):            
            return ro.callRemote('sendSignal', 'MATCH')

        d.addCallback( lambda _: self.get_proxy() )

        d.addCallback(on_proxy)

        def check_result( result ):
            self.assertEquals( result.body[0], 'Signal arg: MATCH' )

        dsig.addCallback(check_result)

        return dsig

    def test_arg_path_rule_match(self):
        dsig = defer.Deferred()

        def on_signal( result ):
            dsig.callback( result )
            
        d = self.client_conn.addMatch( on_signal,
                                       mtype     = 'signal',
                                       sender    = self.tst_bus,
                                       arg_path  = [(0,'/aa/bb/')])
        
        def on_proxy( ro ):            
            return ro.callRemote('sendRaw', '/aa/bb/cc')

        d.addCallback( lambda _: self.get_proxy() )

        d.addCallback(on_proxy)

        def check_result( result ):
            self.assertEquals( result.body[0], '/aa/bb/cc' )

        dsig.addCallback(check_result)

        return dsig

    def test_arg_rule_remove_match(self):
        dsig = defer.Deferred()

        x = dict(rule_id=None)
        
        def on_signal( result ):
            dsig.callback( result )
            
        d = self.client_conn.addMatch( on_signal,
                                       mtype     = 'signal',
                                       sender    = self.tst_bus,
                                       arg       = [(0,'Signal arg: MATCH')])

        def added(rule_id):
            x['rule_id'] = rule_id
            return self.get_proxy()

        d.addCallback( added )
        
        def on_proxy( ro ):            
            return ro.callRemote('sendSignal', 'MATCH')

        d.addCallback(on_proxy)

        def check_result( result ):
            self.assertEquals( result.body[0], 'Signal arg: MATCH' )

        dsig.addCallback(check_result)

        def remove(_):
            return self.client_conn.delMatch(x['rule_id'])

        dsig.addCallback( remove )

        return dsig
    

    

class ErrorTester(ServerObjectTester):
    class TestException (Exception):
        dbusErrorName = 'org.txdbus.trial.TestException'
        pass

    class InvalidErrorName (Exception):
        dbusErrorName = 'oops'
        
    
    class TestClass (objects.DBusObject):

        tif = DBusInterface( 'org.txdbus.trial.Oops',
                             Method('errCall', arguments='s'),
                             Method('raiseExpected'),
                             Method('raisePython'),
                             Method('raiseInvalid'),
                             Signal('testSignal', 's')
                             )

        dbusInterfaces = [tif]

        def __init__(self, object_path):
            objects.DBusObject.__init__(self, object_path)


        def dbus_errCall(self, arg):
            self.fail( 'Should not see this')

        def dbus_raiseExpected(self):
            raise ErrorTester.TestException('ExpectedError')

        def dbus_raisePython(self):
            d = dict()
            d['Uh oh!']

        def dbus_raiseInvalid(self):
            raise ErrorTester.InvalidErrorName()


    def test_err_no_method(self):        
        def on_err( e ):
            self.assertEquals('org.freedesktop.DBus.Error.UnknownMethod: Method "FooBarBaz" with signature "" on interface "(null)" doesn\'t exist',
                              str(e.value))

        d = self.client_conn.callRemote( self.tst_path, 'FooBarBaz',
                                         destination = self.tst_bus )

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d


    def test_err_no_object(self):        
        def on_err( e ):
            self.assertEquals('org.freedesktop.DBus.Error.UnknownObject: /TestObjINVALID is not an object provided by this process.',
                              str(e.value))

        d = self.client_conn.callRemote( self.tst_path + "INVALID", 'FooBarBaz',
                                         destination = self.tst_bus )

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d

    
    def test_err_call_no_arguments(self):        
        def on_err( e ):
            self.assertEquals(str(e.value),
                              'org.freedesktop.DBus.Error.InvalidArgs: Call to errCall has wrong args (, expected s)')

        d = self.client_conn.callRemote( self.tst_path, 'errCall',
                                         destination = self.tst_bus )

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d

    
    def test_err_call_bad_arguments(self):
        def on_err( e ):
            self.assertEquals( str(e.value),
                               'org.freedesktop.DBus.Error.InvalidArgs: Call to errCall has wrong args (i, expected s)' )
            self.assertTrue(True)

        d = self.client_conn.callRemote( self.tst_path, 'errCall',
                                         signature = 'i', body = [5],
                                         destination = self.tst_bus)

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d

    
    def test_raise_expected(self):
        def on_err( e ):
            self.assertEquals( str(e.value),
                               'org.txdbus.trial.TestException: ExpectedError' )

        d = self.client_conn.callRemote( self.tst_path, 'raiseExpected',
                                         destination = self.tst_bus )



        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d


    def test_raise_python(self):
        def on_err( e ):
            self.assertEquals( str(e.value),
                               "org.txdbus.PythonException.KeyError: 'Uh oh!'" )

        d = self.client_conn.callRemote( self.tst_path, 'raisePython',
                                         destination = self.tst_bus )



        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d

    
    def test_raise_invalid(self):
        def on_err( e ):
            self.assertEquals( str(e.value),
                               'org.txdbus.InvalidErrorName: !!(Invalid error name "oops")!! ')

        d = self.client_conn.callRemote( self.tst_path, 'raiseInvalid',
                                         destination = self.tst_bus )



        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d
        

    def _test_bad(self):
        def on_err( e ):
            print(str(e.value))
            print(str(e.value.message))
            self.assertTrue(True)

        d = self.client_conn.callRemote( '/org/freedesktop/DBus', 'RequestName',
                            interface   = 'org.freedesktop.DBus',
                            signature = 'i',
                            body = [5],
                            destination = 'org.freedesktop.DBus' )

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d

        
        
class ComplexObjectTester(ServerObjectTester):
    class TestClass (objects.DBusObject):

        tif = DBusInterface( 'org.txdbus.trial.Complex',
                             Method('testComplexArgs', arguments='s(ii(si)i)', returns='s' ),
                             Method('testDictToTuples', arguments='a{ss}', returns='a(ss)' ),
                             Method('testDictToTuples2', arguments='a{ss}', returns='a(ss)y' ),
                             Method('testDictToTuples3', arguments='a{ss}', returns='ia(ss)y' ),
                             Method('testDictToTuples4', arguments='(a{ss})', returns='(ia(ss)y)' ),
                             Method('testCaller'),
                             Method('testTimeOut'),
                             Method('testTimeOutNotNeeded', arguments='s'),
                             Method('notImplemented'),
                             Signal('tsig', 's')
                             )

        dbusInterfaces = [tif]

        def __init__(self, object_path):
            objects.DBusObject.__init__(self, object_path)

            
        def dbus_testComplexArgs(self, arg1, arg2):
            return repr(arg1) + ' # ' + repr(arg2)

        def dbus_testDictToTuples(self, d):
            k = d.keys()
            k.sort()
            r = [(x,d[x]) for x in k]
            return [(x,d[x]) for x in k]

        def dbus_testDictToTuples2(self, d):
            k = d.keys()
            k.sort()
            r = [(x,d[x]) for x in k]
            return ([(x,d[x]) for x in k], 6)

        def dbus_testDictToTuples3(self, d):
            k = d.keys()
            k.sort()
            r = [(x,d[x]) for x in k]
            return (2, [(x,d[x]) for x in k], 6)
        
        def dbus_testDictToTuples4(self, tpl):
            d = tpl[0]
            k = d.keys()
            k.sort()
            r = [(x,d[x]) for x in k]
            return (2, [(x,d[x]) for x in k], 6)


        def dbus_testCaller(self, dbusCaller = None):
            if dbusCaller is None:
                raise Exception('dbusCaller should not be none')

        def dbus_testTimeOut(self):
            d = defer.Deferred()
            reactor.callLater(0.02, lambda : d.callback(None))
            return d

        def dbus_testTimeOutNotNeeded(self, arg):
            if arg == 'err':
                raise Exception('err')
            return 'foo'


    def test_comlex_args(self):

        class Sub:
            dbusOrder = ['substr', 'subint']
            def __init__(self):
                self.substr = 'substring'
                self.subint = 10

        class Foo:
            dbusOrder = ['one', 'two', 'sub', 'four']
            def __init__(self):
                self.one = 1
                self.two = 2
                self.sub = Sub()
                self.four = 4
            

        def got_object(ro):
            return ro.callRemote('testComplexArgs', 'foo', Foo())

        def got_reply(reply):
            self.assertEquals(reply, "u'foo' # [1, 2, [u'substring', 10], 4]")

        return self.proxy_chain(got_object, got_reply)

    def test_dict_to_tuples(self):
        d = dict( foo = 'bar', baz = 'quux', william = 'wallace' )

        def got_object(ro):
            return ro.callRemote('testDictToTuples', d)

        def got_reply(reply):
            self.assertEquals(reply, [['baz', 'quux'], ['foo', 'bar'], ['william', 'wallace']])

        return self.proxy_chain(got_object, got_reply)

    def test_dict_to_tuples2(self):
        d = dict( foo = 'bar', baz = 'quux', william = 'wallace' )

        def got_object(ro):
            return ro.callRemote('testDictToTuples2', d)

        def got_reply(reply):
            self.assertEquals(reply[0], [['baz', 'quux'], ['foo', 'bar'], ['william', 'wallace']])
            self.assertEquals(reply[1], 6)

        return self.proxy_chain(got_object, got_reply)

    def test_dict_to_tuples3(self):
        d = dict( foo = 'bar', baz = 'quux', william = 'wallace' )

        def got_object(ro):
            return ro.callRemote('testDictToTuples3', d)

        def got_reply(reply):
            self.assertEquals(reply[0], 2)
            self.assertEquals(reply[1], [['baz', 'quux'], ['foo', 'bar'], ['william', 'wallace']])
            self.assertEquals(reply[2], 6)

        return self.proxy_chain(got_object, got_reply)

    def test_dict_to_tuples4(self):
        d = dict( foo = 'bar', baz = 'quux', william = 'wallace' )

        def got_object(ro):
            return ro.callRemote('testDictToTuples4', [d])

        def got_reply(reply_obj):
            reply = reply_obj[0]
            self.assertEquals(reply[0], 2)
            self.assertEquals(reply[1], [['baz', 'quux'], ['foo', 'bar'], ['william', 'wallace']])
            self.assertEquals(reply[2], 6)

        return self.proxy_chain(got_object, got_reply)

    def test_caller(self):
        def got_object(ro):
            return ro.callRemote('testCaller')
            
        def got_reply(reply):
            self.assertTrue(True)

        return self.proxy_chain(got_object, got_reply)


    def test_time_out(self):

        def on_proxy(ro):
            return ro.callRemote('testTimeOut', timeout = 0.01)

        def on_err(err):
            self.assertTrue( isinstance(err.value, error.TimeOut), 'Did not receive a timeout' )

        d = self.get_proxy()
        d.addCallback( on_proxy )
        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        d.addBoth( delay )
        return d

    def test_time_out_not_needed(self):

        def on_proxy(ro):

            return ro.callRemote('testTimeOutNotNeeded', '', timeout = 5)

        def on_err(err):
            self.assertTrue( not isinstance(err.value, error.TimeOut), 'Should not have received a timeout' )

        d = self.get_proxy()
        d.addCallback( on_proxy )
        d.addErrback( on_err )
        return d

    def test_time_out_not_needed_on_error(self):

        def on_proxy(ro):

            return ro.callRemote('testTimeOutNotNeeded', 'err', timeout = 5)

        def on_err(err):
            self.assertTrue( not isinstance(err.value, error.TimeOut), 'Should not have received a timeout' )

        d = self.get_proxy()
        d.addCallback( on_proxy )
        d.addErrback( on_err )
        return d

    def test_not_implemented_dbus_method(self):

        def on_proxy(ro):

            return ro.callRemote('notImplemented')

        def on_err(err):
            self.assertEquals(err.getErrorMessage(), 'org.txdbus.PythonException.NotImplementedError' )

        d = self.get_proxy()
        d.addCallback( on_proxy )
        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        d.addBoth( delay )
        return d

    def test_connection_lost_callbacks(self):
        x = dict(hit=False)
        def cb(conn, reason):
            x['hit'] = True

        self.client_conn.notifyOnDisconnect(cb)
        self.client_conn.disconnect()
        self.client_conn = None

        d = delay(0.01)
        d.addCallback( lambda _: self.assertTrue( x['hit'] ) )
        return d

    def test_connection_lost_callbacks_canceled(self):
        x = dict(hit1=False,hit2=False)
        def cb1(conn, reason):
            x['hit1'] = True

        def cb2(conn, reason):
            x['hit2'] = True

        self.client_conn.notifyOnDisconnect(cb2)
        self.client_conn.notifyOnDisconnect(cb1)
        self.client_conn.cancelNotifyOnDisconnect(cb2)
        self.client_conn.disconnect()
        self.client_conn = None

        d = delay(0.01)
        d.addCallback( lambda _: self.assertTrue( x['hit1'] ) )
        d.addCallback( lambda _: self.assertTrue( not x['hit2'] ) )
        return d

    def test_connection_lost_with_pending_calls(self):
        x = dict(hit=False)
        def cb(conn, reason):
            x['hit'] = True

        pending = reactor.callLater(0.1, lambda : self.assertTrue(False, 'Failed to cancel pending call'))
        dcancel = defer.Deferred()

        dcancel.addCallback( lambda _: self.assertTrue(False) )
        dcancel.addErrback( lambda _: self.assertTrue(True) )

        # Directly inject
        self.client_conn._pendingCalls[ 'foo' ] = (dcancel, pending)

        self.client_conn.notifyOnDisconnect(cb)
        self.client_conn.disconnect()
        self.client_conn = None

        d = delay(0.01)
        d.addCallback( lambda _: dcancel )
        return d

    


        
    
    


class InterfaceTester(ServerObjectTester):
    class TestClass (objects.DBusObject):

        tif1 = DBusInterface( 'org.txdbus.trial.IFace1',
                              Method('testMethod', arguments='s', returns='s' ),
                              Method('foo'),
                              Method('baz', returns='s'),
                              Method('blah', returns='vv'),
                              Method('onlyOneImpl'),
                              Property('prop_if1', 's', writeable=True),
                              Property('common', 's')
                             )
        tif2 = DBusInterface( 'org.txdbus.trial.IFace2',
                              Method('testMethod', arguments='s', returns='s' ),
                              Method('bar'),
                              Method('baz', returns='s'),
                              Method('renamedMethod', returns='s'),
                              Method('onlyOneImpl'),
                              Property('prop1', 's'),
                              Property('prop2', 'i'),
                              Property('pwrite', 's', writeable=True),
                              Property('wronly', 's', readable=False, writeable=True),
                              Property('common', 's')
                             )

        dbusInterfaces = [tif1, tif2]


        pif1       = DBusProperty('prop_if1')
        prop_attr  = DBusProperty('prop1', 'org.txdbus.trial.IFace2')
        prop2_attr = DBusProperty('prop2')
        propw      = DBusProperty('pwrite')
        pwr        = DBusProperty('wronly')
        common1    = DBusProperty('common', 'org.txdbus.trial.IFace1')
        common2    = DBusProperty('common', 'org.txdbus.trial.IFace2')
        

        def __init__(self, object_path):
            x = self.pif1 # test property access prior to object construction
            
            objects.DBusObject.__init__(self, object_path)

            self.prop_attr = 'foobar'
            self.prop2_attr = 5
            self.propw      = 'orig'
            self.pwr        = 'blah'
            self.pif1       = 'pif1'
            self.common1    = 'common1'
            self.common2    = 'common2'

        


        def dbus_testMethod(self, arg):
            return arg + 'bar'

        def dbus_foo(self):
            return None

        def dbus_bar(self):
            return None

        def dbus_blah(self):
            return ('foo', 'bar')

        @dbusMethod('org.txdbus.trial.IFace1', 'baz')
        def dbus_baz1(self):
            return 'iface1'

        @dbusMethod('org.txdbus.trial.IFace2', 'baz')
        def dbus_baz2(self):
            return 'iface2'

        @dbusMethod('org.txdbus.trial.IFace2', 'renamedMethod')
        def dbus_sneaky(self):
            return 'sneaky'

        @dbusMethod('org.txdbus.trial.IFace1', 'onlyOneImpl')
        def dbus_onlyOneImpl(self):
            pass

    def test_property_emitsOnChange_validity(self):
        def c():
            Property('foo', 's', emitsOnChange='foo')
        self.assertRaises(TypeError, c)

    def test_interface_invalid_constructor_argument(self):
        def c():
            DBusInterface( 'foo', 1 )
        self.assertRaises(TypeError, c)

    def test_delete_iterface_method(self):
        i = DBusInterface( 'foo', Method('methA'), Method('methB') )
        self.assertTrue( 'methA' in i.introspectionXml )
        i.delMethod('methA')
        self.assertTrue( 'methA' not in i.introspectionXml )

    def test_delete_iterface_signal(self):
        i = DBusInterface( 'foo', Signal('sigA'), Signal('sigB') )
        self.assertTrue( 'sigA' in i.introspectionXml )
        i.delSignal('sigA')
        self.assertTrue( 'sigA' not in i.introspectionXml )

    def test_delete_iterface_property(self):
        i = DBusInterface( 'foo', Property('propA', 'i'), Property('propB', 'i') )
        self.assertTrue( 'propA' in i.introspectionXml )
        i.delProperty('propA')
        self.assertTrue( 'propA' not in i.introspectionXml )

    def test_renamed_server_method(self):
        def got_object(ro):
            return ro.callRemote('renamedMethod')

        def got_reply(reply):
            self.assertEquals(reply, 'sneaky')

        return self.proxy_chain(got_object, got_reply)


    def test_get_proxy_with_string_interface_name(self):
        def got_object(ro):
            return self.client_conn.getRemoteObject( self.tst_bus, self.tst_path, interfaces='org.txdbus.trial.IFace1' )

        def got_object2(ro2):
            return ro2.callRemote('baz')
        
        def got_reply(reply):
            self.assertEquals(reply, 'iface1')

        return self.proxy_chain(got_object, got_object2, got_reply)

    def test_get_proxy_with_bad_interface_name(self):
        def got_object(ro):
            return self.client_conn.getRemoteObject( self.tst_bus, self.tst_path, interfaces='org.txdbus.INVALID_INTERFACE' )

        def on_err(err):
            self.assertEquals(err.getErrorMessage(), 'Introspection failed to find interfaces: org.txdbus.INVALID_INTERFACE' )

        def got(v):
            print('GOT: ', v)

        d = self.get_proxy()
        d.addCallback( got_object )
        d.addCallback(got)
        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d
    
    def test_missing_implementation(self):
        def got_object(ro):
            return ro.callRemote('onlyOneImpl', interface='org.txdbus.trial.IFace2')

        def on_err(err):
            self.assertEquals(err.getErrorMessage(), 'org.txdbus.PythonException.NotImplementedError' )

        d = self.get_proxy()
        d.addCallback( got_object )
        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d

    def test_emit_invalid_signal(self):
        def got_object(ro):
            try:
                self.t.emitSignal('InvalidSignalName')
                self.assertTrue(False, 'Should have raised an exception')
            except AttributeError as e:
                self.assertEquals(str(e), 'Signal "InvalidSignalName" not found in any supported interface.')        

        return self.proxy_chain(got_object)

    
    def test_baz(self):
        def got_object(ro):
            return ro.callRemote('baz')

        def got_reply(reply):
            self.assertEquals(reply, 'iface1')

        return self.proxy_chain(got_object, got_reply)


    def test_baz2(self):
        def got_object(ro):
            return ro.callRemote('baz', interface='org.txdbus.trial.IFace2')

        def got_reply(reply):
            self.assertEquals(reply, 'iface2')

        return self.proxy_chain(got_object, got_reply)
    
    
    def test_foo(self):

        def got_object(ro):
            return ro.callRemote('foo')

        def got_reply(reply):
            self.assertTrue(True)

        return self.proxy_chain(got_object, got_reply)

    
    def test_bad_remote_method(self):
        def got_object(ro):
            self.assertRaises(AttributeError, ro.callRemote, 'INVALID_METHOD_NAME')

        return self.proxy_chain(got_object)


    def test_bad_remote_method_argument_number(self):
        def got_object(ro):
            self.assertRaises(TypeError, ro.callRemote, 'foo', 'bar')

        return self.proxy_chain(got_object)

    
    def test_bar(self):

        def got_object(ro):
            return ro.callRemote('bar')

        def got_reply(reply):
            self.assertTrue(True)

        return self.proxy_chain(got_object, got_reply)


    def test_foo(self):

        def got_object(ro):
            return ro.callRemote('testMethod', 'foo')

        def got_reply(reply):
            self.assertEquals(reply, 'foobar')

        return self.proxy_chain(got_object, got_reply)


    def test_muli_variant_return(self):

        def got_object(ro):
            return ro.callRemote('blah')

        def got_reply(reply):
            self.assertEquals(reply, ['foo', 'bar'])

        return self.proxy_chain(got_object, got_reply)

    
    def test_get_property_with_interface(self):

        def got_object(ro):
            return ro.callRemote('Get', 'org.txdbus.trial.IFace2', 'prop1')

        def got_reply(reply):
            self.assertEquals(reply, 'foobar')

        return self.proxy_chain(got_object, got_reply)

    
    def test_get_common_property1_with_interface(self):

        def got_object(ro):
            return ro.callRemote('Get', 'org.txdbus.trial.IFace1', 'common')

        def got_reply(reply):
            self.assertEquals(reply, 'common1')

        return self.proxy_chain(got_object, got_reply)

    def test_get_common_property2_with_interface(self):

        def got_object(ro):
            return ro.callRemote('Get', 'org.txdbus.trial.IFace2', 'common')

        def got_reply(reply):
            self.assertEquals(reply, 'common2')

        return self.proxy_chain(got_object, got_reply)

    
    def test_get_property_without_interface(self):

        def got_object(ro):
            return ro.callRemote('Get', '', 'prop1')

        def got_reply(reply):
            self.assertEquals(reply, 'foobar')

        return self.proxy_chain(got_object, got_reply)

    
    def test_get_integer_property(self):

        def got_object(ro):
            return ro.callRemote('Get', '', 'prop2')

        def got_reply(reply):
            self.assertEquals(reply, 5)

        return self.proxy_chain(got_object, got_reply)


    def test_get_invalid_property(self):

        def got_object(ro):
            return ro.callRemote('Get', '', 'INVALID_PROPERTY')

        def got_err(err):
            self.assertEquals(err.getErrorMessage(), 'org.txdbus.PythonException.Exception: Invalid Property')

        d = self.get_proxy()
        d.addCallback(got_object)
        d.addErrback(got_err)
        return d

    def test_set_invalid_property(self):

        def got_object(ro):
            return ro.callRemote('Set', '', 'INVALID_PROPERTY', 'Whoopsie')

        def got_err(err):
            self.assertEquals(err.getErrorMessage(), 'org.txdbus.PythonException.Exception: Invalid Property')

        d = self.get_proxy()
        d.addCallback(got_object)
        d.addErrback(got_err)
        return d


    def test_set_read_only_property(self):

        def got_object(ro):
            return ro.callRemote('Set', '', 'prop1', 'Whoopsie')

        def got_err(err):
            self.assertEquals(err.getErrorMessage(), 'org.txdbus.PythonException.Exception: Property is not Writeable')

        d = self.get_proxy()
        d.addCallback(got_object)
        d.addErrback(got_err)
        return d


    def test_get_write_only_property(self):

        def got_object(ro):
            return ro.callRemote('Get', '', 'wronly')

        def got_err(err):
            self.assertEquals(err.getErrorMessage(), 'org.txdbus.PythonException.Exception: Property is not readable')

        d = self.get_proxy()
        d.addCallback(got_object)
        d.addErrback(got_err)
        return d



    def test_set_string_property(self):

        def got_object(ro):
            self.assertEquals(self.t.propw, 'orig')
            return ro.callRemote('Set', '', 'pwrite', 'changed')

        def got_reply(reply):
            self.assertEquals(self.t.propw, 'changed')

        return self.proxy_chain(got_object, got_reply)


    def test_get_all_properties(self):

        def got_object(ro):
            return ro.callRemote('GetAll', '')

        def got_reply(reply):
            self.assertEquals(reply, {'common'   : 'common1',
                                      'prop1'    : 'foobar',
                                      'prop2'    : 5,
                                      'prop_if1' : 'pif1',
                                      'pwrite'   : 'orig'})

        return self.proxy_chain(got_object, got_reply)


    def test_property_emit_changed(self):        
        dsig = defer.Deferred()
        
        def on_signal( *args ):
            dsig.callback(args)

        def check_results(arg):
            interface_name, changed, invalidated = arg
            
            self.assertEquals(interface_name, 'org.txdbus.trial.IFace2')
            self.assertEquals(changed, {'pwrite' : 'should emit'})
            self.assertEquals(invalidated, [])
            
        def on_proxy( ro ):
            dnot = ro.notifyOnSignal('PropertiesChanged', on_signal)
            dnot.addCallback( lambda _: ro )
            return dnot

        def setit(ro):
            ro.callRemote('Set', '', 'pwrite', 'should emit')

        d = self.get_proxy()

        d.addCallback(on_proxy)
        d.addCallback(setit)
        d.addCallback( lambda _: dsig )
        d.addCallback( check_results )

        return d

    def test_property_delete(self):
        def d():
            del self.pif1
        self.assertRaises(AttributeError, d)


    def test_invalid_property_name(self):
        class T(objects.DBusObject):
            prop = DBusProperty('no_interface_property')

        t = T('/foo')
        def ii():
            for x in t._iterIFaceCaches():
                pass

        self.assertRaises(AttributeError, ii)



class BusNameTest(SimpleObjectTester):
    
    def test_get_bus_name(self):

        d = self.client_conn.requestBusName('org.test.foobar')

        def cb( i ):
            self.assertEquals( i, client.NAME_ACQUIRED )
        
        d.addCallback( cb )
        return d

    def test_bad_bus_name(self):
        def on_err( e ):
            self.assertEquals('org.freedesktop.DBus.Error.InvalidArgs: Cannot acquire a service starting with \':\' such as ":1.234"',
                              str(e.value))

        d = self.client_conn.requestBusName(':1.234')
        
        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )
        return d

    def test_already_owner(self):
        d = self.client_conn.requestBusName('org.test.foobar')
            
        def cb( i ):
            self.assertEquals( i, client.NAME_ALREADY_OWNER )
            
        d.addCallback( lambda _: self.client_conn.requestBusName('org.test.foobar') )
        d.addCallback( cb )
        return d
    

    def cli2(self):
        f = client.DBusClientFactory()

        point = endpoints.getDBusEnvEndpoints(reactor)[0]
        point.connect(f)

        d = f.getConnection()

        def got_connection(c):
            self.client_conn2 = c
            return c
            
        d.addCallback(got_connection)
            
        return d

    def test_name_in_use(self):
        d = self.cli2()
        
        d.addCallback( lambda _:  self.client_conn.requestBusName('org.test.foobar') )

        d.addCallback( lambda _:  self.client_conn2.requestBusName('org.test.foobar') )

        def on_err( e ):
            self.assertEquals('Failed to acquire bus name "org.test.foobar": Name in use',
                              str(e.value))

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )

        def cleanup(x):
            self.client_conn2.disconnect()
            return x
        
        d.addBoth( cleanup )
        
        return d


    def test_name_replacement(self):
        d = self.cli2()

        flags = dict(sig = False)
        
        def on_name_lost(sig):
            self.assertEquals(sig.body[0], 'org.test.foobar')
            flags['sig'] = True
        
        d.addCallback( lambda _: self.client_conn.addMatch(on_name_lost, member='NameLost') )
        
        d.addCallback( lambda _:  self.client_conn.requestBusName('org.test.foobar',
                                                                  allowReplacement = True) )

        d.addCallback( lambda _:  self.client_conn2.requestBusName('org.test.foobar',
                                                                   replaceExisting  = True) )

        d.addCallback( delay )
        
        def cb( i ):
            self.assertTrue(flags['sig'])
            self.assertEquals( i, client.NAME_ACQUIRED )
            
        d.addCallback( cb )

        def cleanup(x):
            self.client_conn2.disconnect()
            return x
        
        d.addBoth( cleanup )
        
        return d


    def test_queued_name_replacement(self):
        d = self.cli2()

        flags = dict(sig = False)
        
        def on_name_acq(sig):
            self.assertEquals(sig.body[0], 'org.test.foobar')
            flags['sig'] = True
        
        d.addCallback( lambda _: self.client_conn2.addMatch(on_name_acq, member='NameAcquired') )
        
        d.addCallback( lambda _: self.client_conn.requestBusName('org.test.foobar',
                                                                 allowReplacement = False) )

        d.addCallback( lambda _: self.client_conn2.requestBusName('org.test.foobar',
                                                                  replaceExisting  = True,
                                                                  doNotQueue = False,
                                                                  errbackUnlessAcquired = False) )

        d.addCallback( lambda r: self.assertEquals(r, client.NAME_IN_QUEUE, 'Queue error') )

        d.addCallback( lambda _: self.client_conn.releaseBusName('org.test.foobar') )

        d.addCallback( lambda r: self.assertEquals(r, client.NAME_RELEASED, 'Failed to release name') )

        d.addCallback( delay )

        d.addCallback( lambda _: self.assertTrue(flags['sig'], 'Failed to acquire name after release') )


        def cleanup(x):
            self.client_conn2.disconnect()
            return x
        
        d.addBoth( cleanup )
        
        return d


    def test_queued_name_replacement_with_errback(self):
        d = self.cli2()

        flags = dict(sig = False)
        
        def on_name_acq(sig):
            self.assertEquals(sig.body[0], 'org.test.foobar')
            flags['sig'] = True
        
        d.addCallback( lambda _: self.client_conn2.addMatch(on_name_acq, member='NameAcquired') )
        
        d.addCallback( lambda _: self.client_conn.requestBusName('org.test.foobar',
                                                                 allowReplacement = False) )

        d.addCallback( lambda _: self.client_conn2.requestBusName('org.test.foobar',
                                                                  replaceExisting  = True,
                                                                  doNotQueue = False ) )

        d.addErrback( lambda e: self.assertEquals(e.getErrorMessage(), 'Failed to acquire bus name "org.test.foobar": Queued for name acquisition') )

        d.addCallback( lambda _: self.client_conn.releaseBusName('org.test.foobar') )

        d.addCallback( lambda r: self.assertEquals(r, client.NAME_RELEASED, 'Failed to release name') )

        d.addCallback( delay )

        d.addCallback( lambda _: self.assertTrue(flags['sig'], 'Failed to acquire name after release') )


        def cleanup(x):
            self.client_conn2.disconnect()
            return x
        
        d.addBoth( cleanup )
        
        return d


    def test_list_queued_owners(self):
        d = self.cli2()
        
        d.addCallback( lambda _: self.client_conn.requestBusName('org.test.foobar',
                                                                 allowReplacement = False) )

        d.addCallback( lambda _: self.client_conn2.requestBusName('org.test.foobar',
                                                                  replaceExisting  = True,
                                                                  doNotQueue = False,
                                                                  errbackUnlessAcquired = False) )

        d.addCallback( lambda r: self.assertEquals(r, client.NAME_IN_QUEUE, 'Queue error') )

        d.addCallback( lambda _: self.client_conn2.listQueuedBusNameOwners('org.test.foobar') )


        d.addCallback( lambda r: self.assertEquals(r,
                                                   [self.client_conn.busName, self.client_conn2.busName ],
                                                   'Bus Name Queue differes from expected value') )

        def cleanup(x):
            self.client_conn2.disconnect()
            return x
        
        d.addBoth( cleanup )
        
        return d

    def test_empty_list_queued_owners(self):

        d = self.client_conn.listQueuedBusNameOwners('org.test.foobar')

        def on_err( e ):
            self.assertEquals('org.freedesktop.DBus.Error.NameHasNoOwner: Could not get owners of name \'org.test.foobar\': no such name',
                              str(e.value))

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )

        return d

    #GetConnectionUnixUser

    def test_get_connection_user(self):
        try:
            import pwd
        except ImportError:
            # non-unix system. just return success
            self.assertTrue(True)
            return 
        
        d = self.cli2()
        
        d.addCallback( lambda _: self.client_conn.requestBusName('org.test.foobar') )
        
        d.addCallback( lambda _: self.client_conn2.getConnectionUnixUser('org.test.foobar') )

        d.addCallback( lambda r: self.assertEquals(r, os.getuid(), 'Failed to get connection user id') )

        def cleanup(x):
            self.client_conn2.disconnect()
            return x
        
        d.addBoth( cleanup )
        
        return d


    def test_bad_get_connection_user1(self):
        try:
            import pwd
        except ImportError:
            # non-unix system. just return success
            self.assertTrue(True)
            return 
        
        d = self.cli2()
        
        d.addCallback( lambda _: self.client_conn.requestBusName('org.test.foobar') )


        d.addCallback( lambda _: self.client_conn2.getConnectionUnixUser('org.MISSING_BUS_NAME') )

        def on_err( e ):
            self.assertEquals('org.freedesktop.DBus.Error.NameHasNoOwner: Could not get UID of name \'org.MISSING_BUS_NAME\': no such name',
                              str(e.value))

        d.addCallbacks( lambda _: self.fail('Call should have failed'),
                        on_err )

        def cleanup(x):
            self.client_conn2.disconnect()
            return x
        
        d.addBoth( cleanup )
        
        return d


