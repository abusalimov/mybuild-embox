from __future__ import print_function

from _compat import *


import functools
import itertools
import sys
from collections import defaultdict
from operator import itemgetter

import ply.yacc

from mybuild_embox.lang_legacy import lex
from mylang import x_ast as ast
from mylang.location import Fileinfo
from mylang.location import Location
from mylang.helpers import rule
from mylang.parse import MySyntaxError

from mybuild import core
from util.prop import cached_property
from util.prop import cached_class_property


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


def py_compile_func(p, expr, self_arg='self'):
    try:
        if isinstance(expr, ast.AST):
            args = ast.x_arguments([ast.x_arg(self_arg)]
                                   if self_arg is not None else [])
            ast_root = ast.Expression(copy_loc(ast.Lambda(args, expr),
                                               expr))
            ast.fix_missing_locations(ast_root)
        else:
            ast_root = ast.parse('lambda {}: ({})'.format(self_arg or '',
                                                          expr),
                                 p.lexer.fileinfo.name, mode='eval')
            ast.increment_lineno(ast_root, p.lineno(0)-1)

        code = compile(ast_root, p.lexer.fileinfo.name, mode='eval')
        return eval(code, p.lexer.module_globals)

    except SyntaxError as e:
        raise MySyntaxError(*e.args)

    except:
        print(ast.dump(ast_root, include_attributes=True))
        raise

def py_eval(p, expr, **self_arg_value):
    if len(self_arg_value) > 1:
        raise ValueError('Too many keyword arguments')
    try:
        self_arg, self_value = self_arg_value.popitem()
    except KeyError:
        self_arg = None

    func = py_compile_func(p, expr, self_arg)

    if self_arg is not None:
        return func(self_value)
    else:
        return func()


class module(core.ModuleMetaBase):
    """An alias with a human-readable name."""


@rule
def p_my_file(p, package, imports, entities):
    """
    my_file : package imports entities debug
    """
    # print package
    return dict(entities)

@rule
def p_debug(p, expr=-1):
    """
    debug : E_PRINT expr
    """
    print(py_eval(p, expr, parser=p.parser), file=sys.stderr)

def p_nodebug(p):
    """
    debug :
    """

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
        func = py_compile_func(p, value)
        setattr(module, name, cached_class_property(func, attr=name))

        if name == 'DefaultImpl':
            func = py_compile_func(p, 'self.{}.__my_value__'.format(name))
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

    for kind, prop_name in {'depends': 'depends',
                            'source': 'files'}.items():
        if kind in members:
            members_list = copy_loc(ast.List(members[kind], ast.Load()),
                                    members[kind][0])
            func = py_compile_func(p, members_list)
            module_ns[prop_name] = cached_property(func, attr=prop_name)

    if super_module is not None:
        bases = (py_eval(p, super_module),)
    else:
        bases = ()

    module_ns['__module__'] = p.lexer.module_globals['__name__']

    option_types = []
    for option_ast in members['option']:
        option = py_eval(p, option_ast)
        if hasattr(option, '__my_value__'):
            ns = option.__dict__
            option = ns.pop('__my_value__')[0]
            option.__dict__.update(ns)
        option_types.append((option._name, option))

    meta = module_class._meta_for_base(option_types=option_types,
                                       metaclass=module)
    ret_module = meta(name, bases, module_ns)

    return (name, ret_module)

# (extends ...)?
@rule
def p_super_module(p, super_module=-1):
    """
    super_module : E_EXTENDS expr
    """
    return super_module

@rule
def p_annotated_module_member(p, annotations, kind_member):
    """
    annotated_module_member : annotations module_member
    """
    kind, members = kind_member

    if annotations:
        member_ns = ast.x_Call(ast.x_Name('__my_new_namespace__'),
                               args=[ast.List(members, ast.Load())])
        for name, value in annotations:
            member_ns.keywords.append(ast.keyword(name, value))
        members = [copy_loc(member_ns, members[0])]

    return kind, members

@rule
def p_module_member(p, kind, value):
    """
    module_member : E_DEPENDS  naked_exprlist
    module_member : E_SOURCE   naked_exprlist
    """
    if kind == 'include':
        kind = 'depends'
    return kind, value

@rule
def p_module_member_option(p, kind, option=-1):
    """
    module_member : E_OPTION option
    """
    return kind, [option]

@rule
def p_module_member_unused(p, member):
    """
    module_member : E_PROVIDES naked_exprlist
    module_member : E_REQUIRES naked_exprlist
    module_member : E_OBJECT   naked_exprlist
    """
    raise NotImplementedError("Module member is not supported: " + member,
                              ploc(p))
    return []

# ( string | number | boolean | type ) name ( = ...)?
@rule
def p_option(p, optype, name_wloc, default_value):
    """
    option : option_type name option_default_value
    """
    name, loc = name_wloc
    ret = set_loc_p(ast.x_Call(ast.x_Name('__my_new_option__'),
                               args=[set_loc(ast.Str(name), loc), optype]), p)
    if default_value is not None:
        ret.args.append(default_value)

    return ret

@rule
def p_option_type(p, kind):
    """
    option_type : E_STRING
    option_type : E_NUMBER
    option_type : E_BOOLEAN
    """
    return set_loc_p(ast.Str(kind), p)

@rule
def p_option_type_reference(p):
    """
    option_type : expr
    """
    raise NotImplementedError("References in options are not supported",
                              ploc(p))

@rule
def p_option_default_value(p, value=-1):
    """
    option_default_value : EQUALS expr
    """
    return value

@rule
def p_none(p):
    """
    option_default_value :
    super_module :
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
def p_list_entries(p, entry, entries=-1):
    """
    imports : import imports
    annotations : annotation annotations
    entities : annotated_type entities
    module_members : annotated_module_member module_members
    """
    entries.append(entry)
    return entries

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


# -------------------------------------------------
# @annotations.
# -------------------------------------------------

@rule
def p_annotation(p, name_wloc=2, trailers=3):
    """
    annotation : E_AT name trailers
    """
    return name_wloc[0], build_chain(trailers, build_node(name_wloc))


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

@rule_wloc
def p_pyatom_bool(p, b):
    """pyatom : E_BOOL"""
    return lambda: ast.x_Name(b.capitalize())

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
def p_naked_exprlist(p, exprlist):
    """naked_exprlist : exprlist"""
    return exprlist[0]

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

