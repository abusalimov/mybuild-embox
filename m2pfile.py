import sys
sys.path.insert(0, "../mybuild")

from _compat import *

from nsloader import pyfile
from m2p_parser import my_parse

class MyFileLoader(pyfile.PyFileLoader):
    """Loads My-files using myfile parser/linker."""

    def defaults_for_module(self, module):
        return dict(self.defaults,
                    __my_module__=module)

    def _exec_module(self, module):
        source_string = self.get_source(self.name)
        res = my_parse(source_string, self.name, module.__dict__)
        module.__dict__.update(res)

