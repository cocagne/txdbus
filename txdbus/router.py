"""
This module implements DBus message matching for routing messages
to interested connections.

@author: Tom Cocagne
"""
import six
from twisted.python import log

# XXX Replace this simple, inefficient implementation with something a bit smarter

_mtypes = { 'method_call'   : 1,
            'method_return' : 2,
            'error'         : 3,
            'signal'        : 4 }


class Rule (object):
    """
    Represents a single match rule
    """
    def __init__(self, callback, _id, router):
        self.callback = callback
        self.id       = _id
        self.router   = router
        self.simple   = list()
        

    def add(self, key, value):
        #if key in ('mtype', 'sender', 'interface', 'member', 'path', 'destination'):
        if key in ('mtype', 'interface', 'member', 'path', 'destination'):
            self.simple.append( (key, value) )
        else:
            setattr(self, key, value)

    def cancel(self):
        self.router.delMatch( self.id )

        
    def match(self, m):
        try:
            for k,v in self.simple:
                if getattr(m,k) != v:
                    return
            
            if hasattr(self, 'path_namespace'):
                if m.path is None or not m.path.startswith(pn):
                    return

            if hasattr(self, 'args') and m.body is not None:
                for idx, val in self.args:
                    if idx >= len(m.body) or m.body[idx] != val:
                        return
                    
            if hasattr(self, 'arg_paths') and m.body is not None:
                for idx, val in self.arg_paths:
                    if idx >= len(m.body) or not m.body[idx].startswith(val):
                        return

            # XXX arg0namespace -- Not quite sure how this one works

            # if we get here, we have a match
            self.callback( m )
        except:
            log.err()



        
class MessageRouter (object):
    """
    Routes DBus messages to callback functions based on match rules as defined
    by the DBus specificiation
    """

    def __init__(self):
        self._id = 0
        self._rules = dict()


    def addMatch(self, callback, mtype=None, sender=None, interface=None,
                 member=None, path=None, path_namespace=None, destination=None,
                 args=None, arg_paths=None, arg0namespace=None):

        #print 'ROUTER ADDING MATCH: ', mtype, path, interface, member, 'arg', arg
        
        r = Rule(callback, self._id, self)

        # Simple
        if mtype:          r.add('_messageType',   mtype)
        if sender:         r.add('sender',         sender)
        if interface:      r.add('interface',      interface)
        if member:         r.add('member',         member)
        if path:           r.add('path',           path)
        if destination:    r.add('destination',    destination)

        # Complex
        if path_namespace: r.add('path_namespace', path_namespace)
        if args:           r.add('args',           args)
        if arg_paths:      r.add('arg_paths',      arg_paths)
        if arg0namespace:  r.add('arg0namespace',  arg0namespace)

        i = self._id
        self._id += 1

        self._rules[ i ] = r
        
        return i


    def delMatch(self, rule_id):
        del self._rules[ rule_id ]


    def routeMessage(self, m):
        #print 'ROUTING MSG', m.interface, m.member
        for r in six.itervalues(self._rules):
            r.match( m )

                    
