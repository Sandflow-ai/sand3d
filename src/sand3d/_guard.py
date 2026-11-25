"""What a program does wrong with an object, said by the next verb that meets it.

- An object a verb used up (the tools of `cut`, `join`, `intersect`; what `merge`
  takes after the first), or one `delete` removed, names the verb and the program
  line that did it.
- The same object passed twice to a verb that takes objects says that `at` moves an
  object, it does not copy it.
- A profile or a path `at` placed and nothing used is the commonest silent mistake:
  `s3d.at(p, x=100)` alone on its line. CPython frees the value at the end of the
  statement; its `__del__` arms an error that the next verb raises.

Nothing here touches geometry. `begin` runs at the entry of every public verb.
"""
import keyword
import weakref

import bpy

from . import _core

#: Objects removed while a program may still hold them: id of the Python object -> (it, message).
_gone = {}
#: The public verbs running: [(verb, the program line that called it, the parameters it wrote)].
calls = []
#: The error a freed, unused `at()` result armed.
pending = None
#: `at()` results not used yet.
_watched = weakref.WeakSet()

#: Why a verb uses up what it takes.
REASONS = {"cut": "a tool is consumed by the boolean", "join": "a tool is consumed by the boolean",
           "intersect": "a tool is consumed by the boolean", "blend": "a part blended into another is used up",
           "merge": "an object merged into the first is used up",
           "at": "at with a list of frames uses the object up and returns one copy per frame: use the list it returns"}
#: Keywords 1.0.0 took away, by verb, and what to write instead.
REMOVED = {
    "at": {"mirror": "at: mirror= is gone in 1.0 — the image across a plane of the parent is "
                     "s3d.transform(ob, mirror=\"x\"), on s3d.copy(ob) to keep the original"},
    "mirror": {"axis": "mirror: axis= is gone in 1.0 — the letter is the coordinate that changes sign: "
                       "s3d.mirror(p, \"x\") is the old axis=\"y\""},
    "hole": {"at": "hole: at= is on= in 1.0 — s3d.hole(ob, d, on=frames or points); on= is the one word for where"},
    "join": {"at": "join: at= is gone in 1.0 — place one copy per frame with at, and join the list: "
                   "s3d.join(ob, s3d.at(tool, on=[frames]))"},
    "cut": {"at": "cut: at= is gone in 1.0 — place one copy per frame with at, and cut the list: "
                  "s3d.cut(ob, s3d.at(tool, on=[frames]))"},
    "loft": {"closed": "loft: closed= is loop= in 1.0 — loop=True joins the last section back to the first, a ring "
                       "with no ends; without it, the two ends of a loft are capped"},
}
#: Verbs whose objects must all be different, from which argument on.
DISTINCT = {"cut": 0, "join": 0, "intersect": 0, "merge": 0, "blend": 0, "group": 1, "assembly": 1, "attach": 2, "at": 0, "transform": 0}


def reset():
    """A new scene: nothing is used up or pending any more, and what the last program
    placed and still holds can be freed without a word."""
    global pending
    for value in list(_watched):
        value._s3d_used = True
    _watched.clear()
    _gone.clear()
    pending = None


def removed(ob):
    """Whether `ob` is a Blender object that has been removed from the file."""
    if not isinstance(ob, bpy.types.ID):
        return False
    try:
        ob.name
    except ReferenceError:
        return True
    return False


def _code(name):
    """A name as a program would write the object in a call: itself if it can be a variable."""
    return name if name.isidentifier() and not keyword.iskeyword(name) else repr(name)


def given(verb, names, inside=None):
    """Which of `names` the program wrote in its call to `verb`, if `verb` is the public
    verb running; for a call from inside the library, `inside` (all of them by default)."""
    if calls and calls[-1][0] == verb:
        return set(names) & calls[-1][2]
    return set(names) if inside is None else set(inside)


def using_up(obs, target):
    """Record that the verb running uses `obs` up on `target` — before it does: whichever
    way it goes, the program's objects are gone after it."""
    if not calls or calls[0][0] not in REASONS:
        return
    verb, line = calls[0][:2]
    for ob in _items(obs):
        if isinstance(ob, bpy.types.Object) and not removed(ob):
            name = _core.given_name(ob)
            copy = name if _code(name) == name else "..."
            keep = "" if verb == "at" else f" To keep it, pass s3d.copy({copy}) to {verb} instead."
            _gone[id(ob)] = (ob, f"{name!r} was used up by {verb}({_code(_core.given_name(target))}, ...) on line "
                                 f"{line}; {REASONS[verb]}.{keep}")


def deleting(ob):
    """Record that the program deletes `ob` with `delete`."""
    if calls and calls[0][0] == "delete":
        name = _core.given_name(ob)
        _gone[id(ob)] = (ob, f"{name!r} was deleted by delete({_code(name)}) on line {calls[0][1]}.")


def watch(value, line):
    """Watch an `at()` result: if it is freed unused, the next verb says so."""
    value._s3d_from = line
    value._s3d_used = False
    _watched.add(value)
    return value


def use(value):
    """`value` was used: no error if it is freed now."""
    if getattr(value, "_s3d_used", True) is False:
        value._s3d_used = True


def freed(value):
    """Called by `__del__`: arm the error if an `at()` result goes unused."""
    global pending
    if getattr(value, "_s3d_used", True) is False and pending is None:
        pending = _unused(value)


def _unused(value):
    from .profile import Placed
    kind = "profile" if isinstance(value, Placed) else "path"
    return f"at() on line {value._s3d_from} placed a {kind} that nothing used; write p = s3d.at(p, ...)"


def _items(args):
    """The objects, placed profiles and paths a call was given: lists opened (not points),
    a handle by its root."""
    from .assembly import Handle
    from .profile import Path, Placed
    for a in args:
        if isinstance(a, (bpy.types.ID, Placed, Path)):
            yield a
        elif isinstance(a, Handle):
            yield a.root
        elif isinstance(a, (list, tuple)) and not (a and isinstance(a[0], (int, float))):
            yield from _items(a)


def begin(verb, args, kwargs):
    """At the entry of a public verb: raise what is pending, refuse what is gone or passed
    twice, and mark what it is given as used."""
    global pending
    for keyword, message in REMOVED.get(verb, {}).items():
        if keyword in kwargs:
            raise TypeError(message)
    if pending is not None:
        message, pending = pending, None
        raise ValueError(f"{verb}: {message}")
    for item in _items(list(args) + list(kwargs.values())):
        if isinstance(item, bpy.types.ID):
            if verb != "delete" and removed(item):
                gone = _gone.get(id(item))
                raise ValueError(f"{verb}: {gone[1]}" if gone else f"{verb}: an object given was removed from the scene")
        else:
            use(item)
    if verb == "export":
        unused = sorted((v._s3d_from, _unused(v)) for v in list(_watched) if v._s3d_used is False)
        if unused:
            raise ValueError(f"{verb}: {unused[0][1]}")
    if verb in DISTINCT:
        obs = [o for o in _items(args[DISTINCT[verb]:]) if isinstance(o, bpy.types.Object)]
        seen = {}
        for o in obs:
            seen[o.as_pointer()] = seen.get(o.as_pointer(), 0) + 1
        for o in obs:
            if seen[o.as_pointer()] > 1:
                name = _core.given_name(o)
                at = name if _code(name) == name else "..."
                raise ValueError(f"{verb}: {name!r} is passed {seen[o.as_pointer()]} times; at moves an object, it "
                                 f"does not copy it: s3d.at({at}, on=s3d.ring(...)) places one copy per frame")
