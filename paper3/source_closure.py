"""Conservative static local import closure for a prospective source freeze.

Includes parent package initializers, relative imports and local modules imported
inside functions. Non-Python data assets must be explicit roots. Dynamic imports
are not inferred; callers must supply their local dependencies explicitly.
"""
import ast
from pathlib import Path


def closure(root, entries):
    root = Path(root).resolve()
    pending = [Path(p).resolve() for p in entries]
    seen = set()

    def module(name):
        parts = name.split('.') if name else []
        for n in range(1, len(parts) + 1):
            init = root.joinpath(*parts[:n], '__init__.py')
            if init.is_file():
                pending.append(init)
        stem = root.joinpath(*parts)
        file = stem.with_suffix('.py')
        if file.is_file():
            pending.append(file)

    while pending:
        path = pending.pop()
        path.relative_to(root)  # Refuse implicit snapshots outside the repo.
        if path in seen:
            continue
        if not path.is_file():
            raise ValueError('missing declared source: '+str(path))
        seen.add(path)
        if path.suffix != '.py':
            continue
        relative = path.relative_to(root)
        package = list(relative.parts[:-1])
        module('.'.join(package))
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = package[:len(package)-node.level+1] if node.level else []
                if node.module:
                    base += node.module.split('.')
                name = '.'.join(base)
                module(name)
                for alias in node.names:
                    if alias.name != '*':
                        module('.'.join(base + [alias.name]))
    return sorted(seen)
