"""sand3d's public surface, read from its source by AST (no bpy).

`surface(package)` -> name -> {"kind": function | class | method | property | value, "params": [...]}.
"""
import ast
from pathlib import Path


def _module(package, name):
    path = package / f"{name.replace('.', '/')}.py"
    return path if path.is_file() else package / name.replace(".", "/") / "__init__.py"


def _definitions(path, package, memo=None):
    """name -> FunctionDef / ClassDef visible at module level, following `from .x import`."""
    memo = {} if memo is None else memo
    if path in memo or not path.is_file():
        return memo.get(path, {})
    defs = memo[path] = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defs[node.name] = node
        elif isinstance(node, ast.ImportFrom) and node.level >= 1:
            base = path.parent
            for _ in range(node.level - 1):
                base = base.parent
            target = _module(base, node.module) if node.module else base / "__init__.py"
            sub = _definitions(target, package, memo)
            for alias in node.names:
                if alias.name in sub:
                    defs[alias.asname or alias.name] = sub[alias.name]
    return defs


def public_names(package):
    for node in ast.parse((package / "__init__.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "__all__" for t in node.targets):
            return list(ast.literal_eval(node.value))
    return []


def params(fn, drop_self=False):
    """[(name, kind, default)] — kind in pos / pos_kw / var / kw / varkw, default as source or None."""
    a = fn.args
    out = []
    positional = a.posonlyargs + a.args
    defaults = [None] * (len(positional) - len(a.defaults)) + [ast.unparse(d) for d in a.defaults]
    for i, (arg, default) in enumerate(zip(positional, defaults)):
        if drop_self and i == 0:
            continue
        out.append((arg.arg, "pos" if i < len(a.posonlyargs) else "pos_kw", default))
    if a.vararg:
        out.append((a.vararg.arg, "var", None))
    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        out.append((arg.arg, "kw", None if default is None else ast.unparse(default)))
    if a.kwarg:
        out.append((a.kwarg.arg, "varkw", None))
    return out


def _is_property(fn):
    return any(getattr(d, "id", None) == "property" for d in fn.decorator_list)


def surface(package):
    package = Path(package)
    defs = _definitions(package / "__init__.py", package)
    out = {}
    for name in public_names(package):
        node = defs.get(name)
        if isinstance(node, ast.FunctionDef):
            out[name] = {"kind": "function", "params": params(node)}
        elif isinstance(node, ast.ClassDef):
            body = [n for n in node.body if isinstance(n, ast.FunctionDef)]
            init = next((n for n in body if n.name == "__init__"), None)
            out[name] = {"kind": "class", "params": params(init, drop_self=True) if init else []}
            for fn in body:
                if fn.name.startswith("_"):
                    continue
                kind = "property" if _is_property(fn) else "method"
                out[f"{name}.{fn.name}"] = {"kind": kind, "params": [] if kind == "property" else
                                            params(fn, drop_self=True)}
        else:
            out[name] = {"kind": "value", "params": []}
    frames = _definitions(package / "frames.py", package)
    for method in ("face", "edge"):
        if isinstance(frames.get(method), ast.FunctionDef):
            out[f"ob.{method}"] = {"kind": "method", "params": params(frames[method], drop_self=True)}
    return out
