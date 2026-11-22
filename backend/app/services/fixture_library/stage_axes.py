"""
Stage Axes
==========

One place for turning a drawing's coordinates into this system's.

A rig here is in metres from the centre of the floor: X across, Y up, -Z
upstage (the booth), +Z toward the rear of the room. MVR and grandMA2 are both
right-handed with Z up. MVR states that in its specification; which way their
Y points relative to the audience is a drawing convention, not a rule, and the
mapping below ASSUMES the usual one: +Y is upstage.

    stage x =  drawing x
    stage y =  drawing z      (height)
    stage z = -drawing y      (so upstage stays negative)

That is a rotation of the axes, not a mirror, so left stays left. If a venue
drew its plot with +Y toward the audience the rig arrives turned front to back,
which the import report says so the operator knows where to look.
"""

import math
from typing import List, Optional, Sequence, Tuple

Vector = Tuple[float, float, float]
Matrix3 = Tuple[Vector, Vector, Vector]

IDENTITY: Matrix3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

AXIS_ASSUMPTION = (
    "Positions were read as Z-up with +Y upstage and turned into this system's axes "
    "(X across, Y up, -Z upstage). If the plot was drawn with +Y toward the audience "
    "the rig will arrive turned front to back."
)


def z_up_to_stage(x: float, y: float, z: float) -> Vector:
    """A Z-up point, already in metres, in stage axes."""
    # "+ 0.0" turns the -0.0 a negated zero leaves behind into 0.0.
    return (float(x) + 0.0, float(z) + 0.0, -float(y) + 0.0)


def stage_to_z_up(x: float, y: float, z: float) -> Vector:
    """The inverse of z_up_to_stage, for writing a rig back out."""
    return (float(x) + 0.0, -float(z) + 0.0, float(y) + 0.0)


def multiply(a: Matrix3, b: Matrix3) -> Matrix3:
    return tuple(
        tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3))
        for r in range(3)
    )  # type: ignore[return-value]


def apply(m: Matrix3, v: Sequence[float]) -> Vector:
    return tuple(sum(m[r][k] * v[k] for k in range(3)) for r in range(3))  # type: ignore[return-value]


def z_up_rotation_to_stage(m: Matrix3) -> Matrix3:
    """A Z-up rotation matrix (acting on column vectors) in stage axes: C M C^T."""
    c: Matrix3 = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0))
    c_t: Matrix3 = ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))
    return multiply(multiply(c, m), c_t)


def _normalised(m: Matrix3) -> Optional[Matrix3]:
    """The matrix with its columns scaled to unit length, or None if one is empty.

    An exported matrix can carry the object's scale; only its turn is wanted.
    """
    columns = []
    for c in range(3):
        column = (m[0][c], m[1][c], m[2][c])
        length = math.sqrt(sum(v * v for v in column))
        if length < 1e-9:
            return None
        columns.append(tuple(v / length for v in column))
    return tuple(tuple(columns[c][r] for c in range(3)) for r in range(3))  # type: ignore[return-value]


def _clean(degrees: float) -> float:
    value = round(degrees, 3)
    if value == -180.0:
        value = 180.0
    return value + 0.0


def stage_rotation_degrees(m: Matrix3) -> Optional[Vector]:
    """(rotation_x, rotation_y, rotation_z) in degrees for a stage-axis rotation.

    Read yaw first: the matrix is Ry(rotation_y) * Rx(rotation_x) * Rz(rotation_z).
    rotation_y is the heading about the vertical, which is the one the views
    draw, and taking it first keeps its whole +/-180 degrees instead of folding
    at 90. Returns None for a matrix that is not a rotation (a zero column).
    """
    unit = _normalised(m)
    if unit is None:
        return None
    sin_x = max(-1.0, min(1.0, -unit[1][2]))
    rx = math.asin(sin_x)
    if abs(sin_x) < 0.9999999:
        ry = math.atan2(unit[0][2], unit[2][2])
        rz = math.atan2(unit[1][0], unit[1][1])
    else:
        # Looking straight up or down: heading and roll are one turn.
        ry = math.atan2(-unit[2][0], unit[0][0])
        rz = 0.0
    return (_clean(math.degrees(rx)), _clean(math.degrees(ry)), _clean(math.degrees(rz)))


def z_up_euler_to_stage(x: float, y: float, z: float) -> Vector:
    """Per-axis turns about Z-up axes as turns about stage axes, in degrees.

    Exact when the fixture is turned about one axis, which is the common case
    (a heading). With two or more non-zero the order they compose in belongs to
    the console and is not known here; callers warn.
    """
    return (float(x) + 0.0, float(z) + 0.0, -float(y) + 0.0)


def is_identity(m: Matrix3, tolerance: float = 1e-6) -> bool:
    return all(
        abs(m[r][c] - IDENTITY[r][c]) <= tolerance for r in range(3) for c in range(3)
    )


def columns_to_matrix(u: Sequence[float], v: Sequence[float], w: Sequence[float]) -> Matrix3:
    """The matrix whose columns are u, v and w: local axes written in the parent's."""
    return (
        (float(u[0]), float(v[0]), float(w[0])),
        (float(u[1]), float(v[1]), float(w[1])),
        (float(u[2]), float(v[2]), float(w[2])),
    )


def rows(m: Matrix3) -> List[List[float]]:
    return [list(row) for row in m]
