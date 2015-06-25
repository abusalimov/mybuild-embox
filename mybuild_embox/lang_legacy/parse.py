import ast
import itertools
from collections import defaultdict
from operator import itemgetter

import ply.yacc

from mybuild_embox.lang_legacy import lex
from mylang.location import Fileinfo
from mylang.location import Location
from mylang.helpers import rule
from mylang.parse import MySyntaxError

from mybuild import core
from util.prop import cached_property
from util.prop import cached_class_property


# Annotations
MANDATORY = 'Mandatory'
DEFAULT_IMPL = 'DefaultImpl'
NO_RUNTIME = 'NoRuntime'
INCLUDE_PATH = 'IncludePath'

tokens = lex.tokens


def ploc(p, i=1):
    i = min(i, len(p)-1)
    return Location(p.lexer.fileinfo, p.lineno(i), p.lexpos(i))

def prepare_property(p, return_value):
    try:
        ast_root = ast.parse('lambda self: ({})'.format(return_value),
                             p.lexer.fileinfo.name, mode='eval')
        ast.increment_lineno(ast_root, p.lineno(0)-1)
        code = compile(ast_root,
                       p.lexer.fileinfo.name, mode='eval')
        return eval(code, p.lexer.module_globals)
    except SyntaxError as e:
        raise MySyntaxError(e.args)


@rule
def p_my_file(p, package, imports, entities):
    """
    my_file : package imports entities
    """
    # print package
    return dict(entities)

# package?
@rule
def p_package(p, qualified_name=-1):
    """
    package : E_PACKAGE qualified_name
    """
    return qualified_name

# import*
@rule
def p_imports(p):
    """
    imports : import imports
    import : E_IMPORT qualified_name_with_wildcard
    """
    raise NotImplementedError("Imports are not supported",
                              ploc(p))

@rule
def p_annotated_type(p, annotations, member_type):
    """
    annotated_type : annotations type
    """
    module = member_type[1]
    for name, value in annotations:
        func = prepare_property(p, value)
        setattr(module, name, cached_class_property(func, attr=name))

        if name == DEFAULT_IMPL:
            func = prepare_property(p, 'self.{}'.format(name))
            module.default_provider = cached_class_property(func,
                                        attr='default_provider')

    return member_type

@rule
def p_type_module(p, module):
    """
    type : module_type
    """
    return module

@rule
def p_type_interface(p, interface):
    """
    type : interface
    """
    raise NotImplementedError("Interfaces and features are not supported",
                              ploc(p))

# -------------------------------------------------
# annotation type.
# -------------------------------------------------

@rule
def p_annotation_type(p):
    """
    type : annotation_type
    annotation_type : E_ANNOTATION ID LBRACE annotation_members RBRACE
    annotation_members : annotated_annotation_member annotation_members
    annotation_members :
    annotated_annotation_member : annotations option
    """
    raise NotImplementedError("Annotations are not supported",
                              ploc(p))


# -------------------------------------------------
# interfaces and features.
# -------------------------------------------------

# interface name (extends ...)? { ... }
@rule
def p_interface(p):
    """
    interface : E_INTERFACE ID super_interfaces LBRACE features RBRACE
    """
    raise NotImplementedError("Interfaces and features are not supported",
                              ploc(p))

# (extends ...)?
@rule
def p_super_interfaces(p):
    """
    super_interfaces : E_EXTENDS reference_list
    super_interfaces :
    """
    raise NotImplementedError("Interfaces and features are not supported",
                              ploc(p))

# annotated_interface_member*
@rule
def p_features(p):
    """
    features : annotated_feature features
    features :
    annotated_feature : annotations feature
    """
    raise NotImplementedError("Interfaces and features are not supported",
                              ploc(p))

# feature name (extends ...)?
@rule
def p_feature(p):
    """
    feature : E_FEATURE ID super_features
    """
    raise NotImplementedError("Interfaces and features are not supported",
                              ploc(p))

# (extends ...)?
@rule
def p_super_features(p):
    """
    super_features : E_EXTENDS reference_list
    super_features :
    """
    raise NotImplementedError("Interfaces and features are not supported",
                              ploc(p))

# -------------------------------------------------
# modules.
# -------------------------------------------------

# (abstract)? module name (extends ...)? { ... }
@rule
def p_module_type(p, modifier, name=3, super_module=4, module_members=-2):
    """
    module_type : module_modifier E_MODULE ID super_module LBRACE module_members RBRACE
    """
    members = defaultdict(list)
    module_class, module_ns = modifier

    if module_members:
        for k, v in module_members:
            members[k] += v

    for key in ['build_depends', 'runtime_depends', 'includes', 'files']:
        if key in members:
            func = prepare_property(p, '[' + ', '.join(members[key]) + ']')
            module_ns[key] = cached_property(func, attr=key)

    if super_module is not None:
        func = prepare_property(p, '[' + name + ', ' + super_module + ']')
        module_ns['provides'] = cached_class_property(func, attr='provides')
        bases = (prepare_property(p, super_module)(None),)
    else:
        bases = ()

    module_ns['__module__'] = p.lexer.module_globals['__name__']

    meta = module_class._meta_for_base(option_types=members['defines'])
    module = meta(name, bases, module_ns)

    return (name, module)

# (extends ...)?
@rule
def p_super_module(p, super_module=-1):
    """
    super_module : E_EXTENDS reference
    """
    return super_module

@rule
def p_annotated_module_member(p, annotations, module_member):
    """
    annotated_module_member : annotations module_member
    """
    for name, value in annotations:
        if name == NO_RUNTIME:
            # Only build depends
            module_member = [module_member[1]]
        elif name == INCLUDE_PATH:
            include = value.replace('(', '{').replace(')', '}')
            module_member.append(('includes', ['\"' + include + '\"']))
        else:
            raise NotImplementedError("Unsupported member annotation {} in {}"
                                      .format(name, module_member),
                                      ploc(p))
    return module_member

@rule
def p_module_member_depends(p, depends_list=-1):
    """
    module_member : E_DEPENDS  reference_wopts_list
    """
    return [('runtime_depends', depends_list), ('build_depends', depends_list)]

@rule
def p_module_member_option(p, option=-1):
    """
    module_member : E_OPTION option
    """
    return [('defines', [option])]

@rule
def p_module_member_source(p, filename_list=-1):
    """
    module_member : E_SOURCE   filename_list
    """
    return [('files', filename_list)]

@rule
def p_module_member_unused(p, member):
    """
    module_member : E_PROVIDES reference_list
    module_member : E_REQUIRES reference_list
    module_member : E_OBJECT   filename_list
    """
    raise NotImplementedError("Module member is not supported: " + member,
                              ploc(p))
    return []

# ( string | number | boolean | type ) name ( = ...)?
@rule
def p_option(p, optype, optid, default_value):
    """
    option : option_type ID option_default_value
    """
    _optype = optype()
    if default_value is not None:
        _optype.set(default=default_value)
    return (optid, _optype.set(name=optid))

@rule
def p_option_str(p):
    """
    option_type : E_STRING
    """
    return core.Optype.str

@rule
def p_option_type_int(p):
    """
    option_type : E_NUMBER
    """
    return core.Optype.int


@rule
def p_option_bool(p):
    """
    option_type : E_BOOLEAN
    """
    return core.Optype.bool

@rule
def p_option_type_reference(p):
    """
    option_type : reference
    """
    raise NotImplementedError("References in options are not supported",
                              ploc(p))

@rule
def p_option_default_value(p, value=-1):
    """
    option_default_value : EQUALS value
    """
    return value

@rule
def p_none(p):
    """
    option_default_value :
    super_module :
    package :
    annotation_initializer :
    """
    return None

@rule
def p_empty(p):
    """
    module_members :
    imports :
    entities :
    annotations :
    """
    return []

@rule
def p_list_listed_entries(p, listed_entry, listed_entries):
    """
    module_members : annotated_module_member module_members
    """
    return listed_entry + listed_entries

@rule
def p_list_entries(p, entry, entries=-1):
    """
    filename_list : filename COMMA filename_list
    parameters_list : parameter COMMA parameters_list
    reference_list : reference COMMA reference_list
    reference_wopts_list : reference_wopts COMMA reference_wopts_list
    annotations : annotation annotations
    entities : annotated_type entities
    """
    entries.append(entry)
    return entries

@rule
def p_list_listed_entry(p, value):
    """
    parameters_list : parameter
    reference_list : reference
    reference_wopts_list : reference_wopts
    """
    return [value]

@rule
def p_list_listed_filename(p, value):
    """
    filename_list :  filename
    """
    return [value]

@rule
def p_empty_modifier_none(p):
    """
    module_modifier :
    """
    func = prepare_property(p, '[tool.cc, tool.gen_headers]')
    ns = dict(tools=cached_property(func, attr='tools'))
    return core.Module, ns

@rule
def p_module_modifier_abstract(p, value):
    """
    module_modifier :  E_ABSTRACT
    """
    func = prepare_property(p, '[]')
    ns = dict(tools=cached_property(func, attr='tools'))
    return core.InterfaceModule, ns

@rule
def p_module_modifier_static(p, value):
    """
    module_modifier : E_STATIC
    """
    func = prepare_property(p, '[tool.cc_lib, tool.gen_headers]')
    static = prepare_property(p, 'True')
    ns = dict(tools=cached_property(func, attr='tools'),
              isstatic=cached_property(static, attr='isstatic'))
    return core.Module, ns

@rule
def p_simple_value(p, value):
    """
    qualified_name : ID
    """
    return value
    ['\"' + value + '\"']

@rule
def p_simple_filename(p, value):
    """
    filename : STRING
    """
    return '\"' + value + '\"'

# -------------------------------------------------
# @annotations.
# -------------------------------------------------

@rule
def p_annotation(p, reference=2, annotation_initializer=3):
    """
    annotation : E_AT reference annotation_initializer
    """
    return (reference, annotation_initializer)

@rule
def p_annotation_initializer(p, value=-2):
    """
    annotation_initializer : LPAREN parameters_list RPAREN
    annotation_initializer :  LPAREN value RPAREN
    """
    return value

# -------------------------------------------------
# comma-separated list of param=value pairs.
# -------------------------------------------------

@rule
def p_parameter(p, reference, value=-1):
    """
    parameter : simple_reference EQUALS value
    """
    return (reference, value)

@rule
def p_value(p, val):
    """
    value : STRING
    value : NUMBER
    value : reference
    reference : qualified_name
    reference_wopts : reference
    simple_reference : ID
    """
    return val

@rule
def p_reference_wopts(p, reference=1, parameters_list=3):
    """
    reference_wopts : reference LPAREN parameters_list RPAREN
    """
    return reference + ', '.join(map('{0[0]!s}={0[1]!r}'.format,
                                     parameters_list)).join('()')

@rule
def p_value_bool(p, val):
    """
    value : E_BOOL
    """
    return val == 'true'


# -------------------------------------------------
# extended identifiers.
# -------------------------------------------------
@rule
def p_qualified_name(p, tire, name=-1):
    """
    qualified_name : ID PERIOD qualified_name
    """
    return tire + '.' + name

@rule
def p_qualified_name_with_wildcard(p):
    """
    qualified_name_with_wildcard : qualified_name E_WILDCARD
    """
    raise NotImplementedError("Wildcard names are not supported",
                              ploc(p))

@rule
def p_qualified_name_without_wildcard(p, qualified_name):
    """
    qualified_name_with_wildcard : qualified_name
    """
    return qualified_name

def p_error(t):
    if t is not None:
        raise MySyntaxError("Unexpected {0!r} token".format(t.value),
                            lex.loc(t))
    else:
        raise MySyntaxError("Premature end of file")

parser = ply.yacc.yacc(start='my_file',
                       # errorlog=ply.yacc.NullLogger(), debug=False,
                       write_tables=False)

def my_parse(source, filename="<unknown>", module_globals=None, **kwargs):
    lx = lex.lexer.clone()

    lx.fileinfo = Fileinfo(source, filename)
    if module_globals is None:
        module_globals = {'__name__': '__main__'}
    lx.module_globals = module_globals
    lx.aux_func_counter = 0

    try:
        result = parser.parse(source, lexer=lx, tracking=True, **kwargs)
    except (MySyntaxError, NotImplementedError) as e:
        raise SyntaxError(*e.args)

    return result

if __name__ == "__main__":
    source = """
package embox.kernel.sched

@DefaultImpl(sched_ticker_preempt)
abstract module sched_ticker { }

module sched_ticker_preempt extends sched_ticker {
    source "sched_ticker.c"
    option number tick_interval = 100
    option string tick_interval = "xxx"
    option boolean tick_interval = false
    @NoRuntime depends embox.kernel.timer.sys_timer /* for timeslices support */
    @NoRuntime depends embox.kernel.timer /* for timeslices support */
    depends embox.kernel /* for timeslices support */
}
"""
    res = my_parse(source, debug=0)
    print res

