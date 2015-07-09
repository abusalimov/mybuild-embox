"""
Runtime support for My-lang.
"""
from __future__ import print_function


__author__ = "Eldar Abusalimov"
__date__ = "2015-06-27"


from _compat import *

from util.namespace import Namespace


builtin_names = [
    # Functions
    'abs',        'all',        'any',        'bin',
    'bool',       'dict',       'filter',     'float',
    'format',     'getattr',    'hasattr',    'hex',
    'id',         'int',        'isinstance', 'issubclass',
    'iter',       'len',        'list',       'map',
    'max',        'min',        'object',     'pow',
    'print',      'range',      'repr',       'reversed',
    'set',        'slice',      'sorted',     'str',
    'sum',        'tuple',      'type',       'zip',

    # Constants
    'False', 'True', 'None',


    # Disabled Python builtins:
    #
    # basestring bytearray callable chr classmethod compile complex delattr
    # dir divmod enumerate eval execfile file frozenset globals hash help input
    # locals long memoryview next oct open ord property raw_input reduce reload
    # round setattr staticmethod super unichr unicode vars xrange __import__
    # apply buffer coerce intern
]


# Note that some name are taken from globals of this module (this includes
# _compat.* as well), and the rest come from Python builtins.
builtins = dict((name, eval(name)) for name in builtin_names)


annotation_names = [
    'AddPrefix',                'App',
    'AutoCmd',                  'Build',
    'BuildArtifactPath',        'BuildDepends',
    'Cflags',                   'Cmd',
    'DefaultImpl',              'DefineMacro',
    'For',                      'Generated',
    'IfNeed',                   'Include',
    'IncludeExport',            'IncludePath',
    'IncludePathBefore',        'InitFS',
    'InstrumentProfiling',      'Mandatory',
    'NoRuntime',                'NumConstraint',
    'Postbuild',                'Rule',
    'Runlevel',                 'TestFor',
    'Type',                     'Unique',
    'WithAllTests',             'WithTest',
    'WithValueNumber',
]

class Annotation(Namespace):

    def __call__(self, *args, **kwargs):
        cls = type(self)
        if args:
            kwargs.update(__my_value__=args[0] if len(args)==1 else list(args))
        ret = cls(**dict(self.__dict__, **kwargs))
        return ret


builtins.update((name, Annotation(__name__=name)) for name in annotation_names)
