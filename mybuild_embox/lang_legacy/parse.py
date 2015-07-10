from __future__ import print_function

from _compat import *


import ast
import functools
import itertools
import sys
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


# Location tracking.

def node_loc(ast_node, p):
    return Location.from_ast_node(ast_node, p.lexer.fileinfo)

def ploc(p, i=1):
    i = min(i, len(p)-1)
    return Location(p.lexer.fileinfo, p.lineno(i), p.lexpos(i))

def set_loc(ast_node, loc):
    return loc.init_ast_node(ast_node)

def set_loc_p(ast_node, p, i=1):
    return set_loc(ast_node, ploc(p, i))

copy_loc = ast.copy_location


def wloc(func):
    @functools.wraps(func)
    def decorated(p, *symbols):
        return func(p, *symbols), ploc(p)
    return decorated

def rule_wloc(func):
    return rule(wloc(func))


def name_builder(name):
    def builder(expr=None):
        if expr is not None:
            return ast.Attribute(expr, name, ast.Load())
        else:
            return ast.x_Name(name)
    return builder

def build_node(builder_wloc, expr=None):
    builder, loc = builder_wloc
    if not callable(builder):
        builder = name_builder(builder)
    return set_loc(builder(expr) if expr is not None else builder(), loc)

def build_chain(builder_wlocs, expr=None):
    for builder_wloc in builder_wlocs:
        expr = build_node(builder_wloc, expr)
    return expr


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
def p_package(p, qualname_wlocs=-1):
    """
    package : E_PACKAGE qualname
    """
    qualname = '.'.join(name for name, loc in qualname_wlocs)
    expected = p.lexer.module_globals['__package__']
    if qualname != expected:
        raise MySyntaxError("Package mismatch, expected '{expected}'"
                            .format(**locals()), ploc(p, 2))

@rule
def p_annotated_type(p, annotations, member_type):
    """
    annotated_type : annotations type
    """
    module_name, module = member_type
    for name, value in annotations:
        func = prepare_property(p, value)
        setattr(module, name, cached_class_property(func, attr=name))

        if name == DEFAULT_IMPL:
            func = prepare_property(p, 'self.{}'.format(name))
            module.default_provider = cached_class_property(func,
                                        attr='default_provider')

    p.lexer.module_globals[module_name] = module
    p.lexer.package_globals[module_name] = module

    return member_type

@rule
def p_type_module(p, module):
    """
    type : module_type
    """
    return module

# -------------------------------------------------
# annotation type.
# interfaces and features.
# import.
# -------------------------------------------------

@rule
def p_not_implemented(p, kind):
    """
    type : E_ANNOTATION ID
    type : E_INTERFACE ID
    import : E_IMPORT
    """
    raise NotImplementedError("'{kind}' types are not supported"
                              .format(**locals()), ploc(p))

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
    imports : import imports
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
    return core.Module, {}

@rule
def p_module_modifier_abstract(p, value):
    """
    module_modifier :  E_ABSTRACT
    """
    return core.InterfaceModule, {}

@rule
def p_module_modifier_static(p, value):
    """
    module_modifier : E_STATIC
    """
    return core.Module, {'isstatic': True}

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


def p_error(t):
    if t is not None:
        raise MySyntaxError("Unexpected {0!r} token".format(t.value),
                            lex.loc(t))
    else:
        raise MySyntaxError("Premature end of file")


# =================================================
# These are derived from a new mylang parser.
# =================================================

@rule
def p_expr(p, expr):
    """expr : pyexpr"""
    return expr

@rule
def p_pyexpr(p, stub, builders):
    """pyexpr : pystub trailers"""
    return build_chain(builders, stub)

@rule
def p_stub(p, builder):
    """pystub : name
       pystub : pyatom"""
    return build_node(builder)


@rule_wloc
def p_pyatom_num(p, n):
    """pyatom : NUMBER"""
    return lambda: ast.Num(n)

@rule
def p_pyatom_string(p, string):
    """pyatom : string"""
    return string

@rule_wloc
def p_string(p, s):
    """string : STRING"""
    return lambda: ast.Str(s)

@rule_wloc
def p_pyatom_parens_or_tuple(p, opentok, exprlist):  # (item, ...), [item, ...]
    """pyatom : LPAREN   exprlist RPAREN
       pyatom : LBRACKET exprlist RBRACKET"""
    expr_l, expr_el = exprlist
    if opentok == '(' and expr_el is not None:
        return lambda: expr_el
    else:
        return lambda: ast.List(expr_l, ast.Load())

@rule_wloc
def p_pyatom_dict(p, kv_pairs=2):  # [key: value, ...], [:]
    """pyatom : LBRACKET dictents RBRACKET
       pyatom : LBRACKET COLON RBRACKET"""
    if kv_pairs != ':':
        keys, values = map(list, zip(*kv_pairs))
    else:
        keys, values = [], []

    return lambda: ast.Dict(keys, values)

@rule
def p_dictent(p, key, value=3):
    """dictent : expr COLON expr"""
    return key, value


@rule
def p_trailer_call(p, call):
    """trailer : call"""
    return call

@rule_wloc
def p_call(p, kw_arg_pairs=2):  # x(arg, kw=arg, ...)
    """call : LPAREN arguments RPAREN"""
    args      = []  # positional arguments
    keywords  = []  # keyword arguments
    seen_kw   = set()

    for kw_wloc, arg in kw_arg_pairs:
        if kw_wloc is None:
            if seen_kw:
                raise MySyntaxError('non-keyword arg after keyword arg',
                                    node_loc(arg, p))
            args.append(arg)

        else:
            kw, loc = kw_wloc
            if kw in seen_kw:
                raise MySyntaxError('keyword argument repeated', loc)
            else:
                seen_kw.add(kw)
            keywords.append(set_loc(ast.keyword(kw, arg), loc))

    return lambda expr: ast.x_Call(expr, args, keywords)

@rule
def p_argument_pos(p, value):
    """argument : expr"""
    return None, value

@rule
def p_argument_kw(p, key, value=3):
    """argument : ID EQUALS expr"""
    kw_wloc = key, ploc(p)
    return kw_wloc, value

@rule_wloc
def p_trailer_attr_or_name(p, name=-1):  # x.attr or name
    """trailer : PERIOD ID
       name    : ID"""
    return name

@rule_wloc
def p_trailer_item(p, item=2):  # x[item]
    """trailer : LBRACKET expr RBRACKET"""
    return lambda expr: ast.Subscript(expr, ast.Index(item), ast.Load())


# exprlist is a pair of [list of elements] and a single element (if any)

@rule
def p_exprlist(p, l):
    """exprlist : exprlist_plus mb_comma"""
    return l

@rule
def p_exprlist_empty(p):
    """exprlist :"""
    return [], None

@rule
def p_exprlist_single(p, el):
    """exprlist_plus : expr"""
    return [el], el

@rule
def p_exprlist_list(p, l_el, el=-1):
    """exprlist_plus : exprlist_plus COMMA expr"""
    l, _ = l_el
    l.append(el)
    return l, None


# generic (possibly comma-separated, and with trailing comma) list parsing

@rule
def p_list_head(p, el):
    """
    qualname           :  name

    arguments_plus     :  argument
    dictents_plus      :  dictent
    """
    return [el]

@rule
def p_list_tail(p, l, el=-1):
    """
    qualname           :  qualname        PERIOD     name

    arguments_plus     :  arguments_plus  COMMA      argument
    dictents_plus      :  dictents_plus   COMMA      dictent

    trailers_plus      :  trailers                   trailer
    """
    l.append(el)
    return l

@rule
def p_list_alias(p, l):
    """
    trailers             :  empty_list
    trailers             :  trailers_plus

    arguments          :  arguments_plus  mb_comma
    dictents           :  dictents_plus   mb_comma

    arguments          :  empty_list
    """
    return l

@rule
def p_empty_list(p):
    """empty_list :"""
    return []

def p_mb_comma(p):
    """mb_comma :
       mb_comma : COMMA"""



# =================================================

parser = ply.yacc.yacc(start='my_file',
                       errorlog=ply.yacc.NullLogger(), debug=False,
                       write_tables=False)

def my_parse(source, filename="<unknown>", module_globals=None, **kwargs):
    lx = lex.lexer.clone()

    lx.fileinfo = Fileinfo(source, filename)

    if module_globals is None:
        module_globals = {'__name__': '__main__', '__package__': None}
    lx.module_globals = module_globals

    if module_globals['__package__'] is not None:
        package_globals = sys.modules[module_globals['__package__']].__dict__
    else:
        package_globals = {}
    lx.package_globals = package_globals

    try:
        result = parser.parse(source, lexer=lx, tracking=True, **kwargs)
    except (MySyntaxError, NotImplementedError) as e:
        raise SyntaxError(*e.args)
    except:
        print("Unable to parse '{}'".format(filename), file=sys.stderr)
        raise

    return result

if __name__ == "__main__":
    source = """
    """
    res = my_parse(source, debug=0)
    print(res)

