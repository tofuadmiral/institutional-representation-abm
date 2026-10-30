"""Same conservative static closure, with immutable parsed-import memoization.

The original source_closure.py is frozen and untouched. This prospective helper
still rereads every source and rechecks every local/absent module path on EVERY
call. Only syntax-to-import-name conversion is memoized by exact text/package;
new files, changed imports, aliases and package initializers remain detectable.
"""
import ast
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=512)
def _imports(source, package):
    names = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = list(package[:len(package)-node.level+1]) if node.level else []
            if node.module:
                base += node.module.split('.')
            name = '.'.join(base)
            names.append(name)
            names.extend('.'.join(base+[alias.name]) for alias in node.names if alias.name != '*')
    return tuple(names)


def closure(root, entries):
    root = Path(root).resolve()
    pending = [Path(p).resolve() for p in entries]
    seen = set()
    def module(name):
        parts = name.split('.') if name else []
        for index in range(1, len(parts)+1):
            init = root.joinpath(*parts[:index], '__init__.py')
            if init.is_file():
                pending.append(init)
        file = root.joinpath(*parts).with_suffix('.py')
        if file.is_file():
            pending.append(file)
    while pending:
        path = pending.pop()
        relative = path.relative_to(root)
        if path in seen:
            continue
        if not path.is_file():
            raise ValueError('missing declared source: '+str(path))
        seen.add(path)
        if path.suffix != '.py':
            continue
        package = tuple(relative.parts[:-1])
        module('.'.join(package))
        for name in _imports(path.read_text(), package):
            module(name)
    return sorted(seen)
