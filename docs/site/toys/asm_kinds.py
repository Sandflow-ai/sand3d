import sand3d as s3d


def kinds():
    parts = []
    for i, kind in enumerate(("revolute", "continuous", "prismatic", "free")):
        base = s3d.at(s3d.box("base", 50, 50, 8), x=i * 80)
        arm = s3d.at(s3d.box(kind, 36, 12, 25), on=s3d.local(base, z=8), x=12)
        options = {"range": (0, 90)} if kind == "revolute" else {"range": (0, 30)} if kind == "prismatic" else {}
        s3d.joint(kind, arm, s3d.local(base, z=8), kind=kind, **options)
        s3d.material(base, "steel")
        s3d.material(arm, "plastic", color="#438d99")
        if kind != "free":
            s3d.pose(arm, 20 if kind == "prismatic" else 60)
        parts.extend([base, arm])
    return s3d.assembly("joint_kinds", parts)
