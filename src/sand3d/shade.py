"""Shading of one part, whatever the program's facets."""
from . import _core


def smooth(ob, angle=55):
    """Shade a part smooth, keeping sharp the edges its faces turn by more than `angle`.

    Whatever `facets` set for the program; a group, an assembly or a list shades each
    of its meshes. The choice follows the part through later edits and copies, and into
    every export. `angle=180` leaves no sharp edge, `angle=0` shades every face flat."""
    from ._surface import meshes
    if isinstance(angle, bool) or not isinstance(angle, (int, float)) or not 0 <= angle <= 180:
        raise ValueError(f'smooth: angle={angle!r} is not a number of degrees from 0 to 180')
    parts = meshes(ob)
    if not parts:
        raise TypeError('smooth: a part, a group, an assembly or a list of them is expected')
    for part in parts:
        if "s3d~merged.shading" in part:
            del part["s3d~merged.shading"]
        _core.own_mesh(part)
        part[_core.SHADE] = float(angle)
    _core.shade_meshes(parts)
    return ob
