"""Writes the binary USD (USDC) test fixtures with Pixar's own USD library.

Run once by hand, outside the backend venv (usd-core is NOT a dependency):
    pip install --target <scratch> usd-core
    PYTHONPATH=<scratch> python tests/fixtures/usdc/make_usdc_fixtures.py
Each fixture gets a JSON next to it with the world-space points and faces
that Pixar's library computes, which the reader's tests compare against.

That run writes crate version 0.8.0, the library's default. The two other
versions of the first room, room_y_metres_v0_7_0 and room_y_metres_v0_10_0,
were made the same way, by calling simple() with the same arguments and those
names while the environment variable USD_WRITE_NEW_USDC_FILES_AS_VERSION was
set to 0.7.0 and to 0.10.0. They are not made by running this file as it is.
"""
import json, os, sys, zipfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "unit"))
from room_scan_meshes import room_mesh, big_room_mesh, as_scanned, box  # noqa: E402
from pxr import Usd, UsdGeom, Gf, Sdf, Vt  # noqa: E402


def add_mesh(stage, path, vertices, faces, extra=True):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, v)) for v in vertices]))
    m.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(faces)))
    m.CreateFaceVertexIndicesAttr(Vt.IntArray([int(i) for f in faces for i in f]))
    if extra:
        # Things a phone app writes that the reader must step over.
        m.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(0, 1, 0)] * len(vertices)))
        m.CreateDoubleSidedAttr(True)
        m.CreateSubdivisionSchemeAttr("none")
        pv = UsdGeom.PrimvarsAPI(m).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
        pv.Set(Vt.Vec2fArray([Gf.Vec2f(0.5, 0.5)] * (3 * len(faces))))
        m.GetPrim().SetMetadata("comment", "fixture")
        m.GetPrim().SetCustomDataByKey("app", "make_usdc_fixtures")
    return m


def truth(stage):
    pts, tris, names = [], [], []
    cache = UsdGeom.XformCache()
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        local = np.array(mesh.GetPointsAttr().Get(), dtype=float)
        mat = np.array(cache.GetLocalToWorldTransform(prim), dtype=float)
        world = np.c_[local, np.ones(len(local))] @ mat
        counts = list(mesh.GetFaceVertexCountsAttr().Get())
        idx = list(mesh.GetFaceVertexIndicesAttr().Get())
        base = sum(len(p) for p in pts)
        k = 0
        for c in counts:
            poly = idx[k:k + c]; k += c
            for j in range(1, c - 1):
                tris.append([base + poly[0], base + poly[j], base + poly[j + 1]])
        pts.append(world[:, :3].tolist()); names.append(str(prim.GetPath()))
    flat = [p for part in pts for p in part]
    return {"up_axis": UsdGeom.GetStageUpAxis(stage).lower(),
            "metres_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
            "meshes": names, "points": flat, "faces": tris}


def save(stage, name):
    stage.GetRootLayer().Save()
    with open(os.path.join(HERE, name + ".json"), "w") as fh:
        json.dump(truth(stage), fh)


def simple(name, up, mpu, vertices, faces, translate):
    path = os.path.join(HERE, name + ".usdc")
    stage = Usd.Stage.CreateNew(path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y if up == "Y" else UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, mpu)
    root = UsdGeom.Xform.Define(stage, "/Room")
    stage.SetDefaultPrim(root.GetPrim())
    root.AddTranslateOp().Set(Gf.Vec3d(*translate))
    add_mesh(stage, "/Room/Scan", vertices, faces)
    save(stage, name)


def roomplan_like(name):
    """Shaped like Apple RoomPlan's export: one prim per wall, floor and object,
    each a unit box mesh placed by a 4x4 matrix, nested in group Xforms, plus
    a scaled and rotated object and a quad-faced (non-triangle) floor."""
    inner = os.path.join(HERE, name + "_layer.usdc")
    stage = Usd.Stage.CreateNew(inner)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Room"); stage.SetDefaultPrim(root.GetPrim())
    for g in ("Parametric_grp", "Parametric_grp/Arch_grp", "Parametric_grp/Object_grp"):
        UsdGeom.Xform.Define(stage, "/Room/" + g)
    W, D, H, T = 12.0, 9.0, 4.0, 0.1
    unit_v, unit_f = box(-0.5, 0.5, -0.5, 0.5, -0.5, 0.5)
    walls = [((0, H / 2, -D / 2), (W, H, T), 0), ((0, H / 2, D / 2), (W, H, T), 0),
             ((-W / 2, H / 2, 0), (D, H, T), 90), ((W / 2, H / 2, 0), (D, H, T), 90)]
    for i, (pos, size, yaw) in enumerate(walls):
        grp = UsdGeom.Xform.Define(stage, f"/Room/Parametric_grp/Arch_grp/Wall_{i}_grp")
        x = UsdGeom.Xform.Define(stage, f"/Room/Parametric_grp/Arch_grp/Wall_{i}_grp/Wall{i}")
        m = Gf.Matrix4d().SetScale(Gf.Vec3d(*size)) * Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 1, 0), yaw)) * Gf.Matrix4d().SetTranslate(Gf.Vec3d(*pos))
        x.AddTransformOp().Set(m)
        add_mesh(stage, x.GetPath().AppendChild("Mesh"), unit_v, unit_f, extra=(i == 0))
    # Floor as quads (4-sided faces), placed by translate + scale ops.
    fl = UsdGeom.Xform.Define(stage, "/Room/Parametric_grp/Arch_grp/Floor0")
    fl.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0)); fl.AddScaleOp().Set(Gf.Vec3f(W, 1, D))
    q = UsdGeom.Mesh.Define(stage, "/Room/Parametric_grp/Arch_grp/Floor0/Mesh")
    q.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(-0.5, 0, -0.5), Gf.Vec3f(0.5, 0, -0.5), Gf.Vec3f(0.5, 0, 0.5), Gf.Vec3f(-0.5, 0, 0.5)]))
    q.CreateFaceVertexCountsAttr(Vt.IntArray([4])); q.CreateFaceVertexIndicesAttr(Vt.IntArray([0, 1, 2, 3]))
    # A stage-like object: orient (quaternion) + translate + scale, the ops in order.
    ob = UsdGeom.Xform.Define(stage, "/Room/Parametric_grp/Object_grp/Table0")
    ob.AddTranslateOp().Set(Gf.Vec3d(0, 0.5, -3.0))
    ob.AddOrientOp().Set(Gf.Quatf(Gf.Rotation(Gf.Vec3d(0, 1, 0), 30).GetQuat()))
    ob.AddScaleOp().Set(Gf.Vec3f(6.0, 1.0, 3.0))
    ob.AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 0))
    add_mesh(stage, "/Room/Parametric_grp/Object_grp/Table0/Mesh", unit_v, unit_f, extra=False)
    # An invisible-to-meshes prim type and a non-mesh with points-like attr: skipped.
    UsdGeom.Scope.Define(stage, "/Room/Looks")
    save(stage, name)
    with zipfile.ZipFile(os.path.join(HERE, name + ".usdz"), "w", zipfile.ZIP_STORED) as z:
        z.write(inner, name + ".usdc")
    os.remove(inner)


if __name__ == "__main__":
    v, f = room_mesh()
    simple("room_y_metres", "Y", 1.0, v, f, (10.0, 0.0, -2.0))
    placed = as_scanned(v, 0.0, up="z", units_per_metre=100.0)
    simple("room_z_cm", "Z", 0.01, placed, f, (0.0, 0.0, 0.0))
    bv, bf = big_room_mesh(with_ring=True, with_angled_truss=True)
    simple("big_room_ring", "Y", 1.0, bv, bf, (0.0, 0.0, 0.0))
    roomplan_like("roomplan_like")
    print("ok", sorted(os.listdir(HERE)))
