import sys
sys.path.append("../mybuild")

import m2p_lex as lex
from mylang.helpers import rule
import ply.yacc

import itertools
from operator import itemgetter


MANDATORY = 'Mandatory'

NO_RUNTIME = 'NoRuntime'

tokens = lex.tokens

# "case sensitive" = true
@rule
def p_my_file(p, package, imports, entities):
    """
    my_file : package imports entities
    """
    print package
    print entities
    return "SOON"

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
    raise NotImplementedError("Imports are not supported")

@rule
def p_annotated_type(p, annotations, member_type):
    """
    annotated_type : annotations type
    """
    return (annotations, member_type)

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
    raise NotImplementedError("Interfaces and features are not supported")

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
    raise NotImplementedError("Annotations are not supported")


# -------------------------------------------------
# interfaces and features.
# -------------------------------------------------

# interface name (extends ...)? { ... }
@rule
def p_interface(p):
    """
    interface : E_INTERFACE ID super_interfaces LBRACE features RBRACE
    """
    raise NotImplementedError("Interfaces and features are not supported")

# (extends ...)?
@rule
def p_super_interfaces(p):
    """
    super_interfaces : E_EXTENDS reference_list
    super_interfaces :
    """
    raise NotImplementedError("Interfaces and features are not supported")

# annotated_interface_member*
@rule
def p_features(p):
    """
    features : annotated_feature features
    features :
    annotated_feature : annotations feature
    """
    raise NotImplementedError("Interfaces and features are not supported")

# feature name (extends ...)?
@rule
def p_feature(p):
    """
    feature : E_FEATURE ID super_features
    """
    raise NotImplementedError("Interfaces and features are not supported")

# (extends ...)?
@rule
def p_super_features(p):
    """
    super_features : E_EXTENDS reference_list
    super_features :
    """
    raise NotImplementedError("Interfaces and features are not supported")

# -------------------------------------------------
# modules.
# -------------------------------------------------

# (abstract)? module name (extends ...)? { ... }
@rule
def p_module_type(p, modifiers, name=3, module_super=4, module_members=-2):
    """
    module_type : module_modifier E_MODULE ID super_module LBRACE module_members RBRACE
    """
    members = dict()
    # print module_members
    if module_members:
        for k, v in module_members:
            members[k] = v if k not in members else members[k] + v
    return (modifiers, name, module_super, members)

# (extends ...)?
@rule
def p_super_module(p, super_module=-1):
    """
    super_module : E_EXTENDS reference
    """
    return super_module

# TODO annotations
@rule
def p_annotated_module_member(p, annotations, module_member):
    """
    annotated_module_member : annotations module_member
    """
    for annotation in annotations:
        if annotation[0] == NO_RUNTIME:
            module_member = [module_member[1]]
        else:
            print annotation, module_member
            raise NotImplementedError("Unsupported annotation")

    return module_member

@rule
def p_module_member_depends(p, depends_list=-1):
    """
    module_member : E_DEPENDS  reference_list
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
def p_module_member_unused(p):
    """
    module_member : E_PROVIDES reference_list
    module_member : E_REQUIRES reference_list
    module_member : E_OBJECT   filename_list
    """
    raise NotImplementedError("Module member is not supported")

# ( string | number | boolean | type ) name ( = ...)?
@rule
def p_option(p, optype, optid, default_value):
    """
    option : option_type ID option_default_value
    """
    return (option_id, option_default_value)

@rule
def p_option_type(p):
    """
    option_type : E_STRING
    option_type : E_NUMBER
    option_type : E_BOOLEAN
    """

@rule
def p_option_type_reference(p):
    """
    option_type : reference
    """
    raise NotImplementedError("References in options are not supported")

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
    module_modifiers :
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
    annotations : annotation annotations
    entities : annotated_type entities
    """
    entries.append(entry)
    return entries

@rule
def p_list_listed_entry(p, value):
    """
    filename_list :  filename
    parameters_list : parameter
    reference_list : reference
    module_modifier : E_STATIC
    module_modifier :  E_ABSTRACT
    """
    return [value]

@rule
def p_simple_value(p, value):
    """
    filename : STRING
    qualified_name : ID
    """
    return value

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
    simple_reference : ID
    """
    return val

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
    raise NotImplementedError("Wildcard names are not supported")

@rule
def p_qualified_name_without_wildcard(p, qualified_name):
    """
    qualified_name_with_wildcard : qualified_name
    """
    return qualified_name

parser = ply.yacc.yacc(start='my_file',
                       # errorlog=ply.yacc.NullLogger(), debug=False,
                       write_tables=False)

def my_parse(source, filename='<unknown>', **kwargs):
    lx = lex.lexer.clone()

    result = parser.parse(source, lexer=lx, tracking=True, **kwargs)
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

