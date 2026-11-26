from pathlib import Path

import sand3d as s3d

LABEL = Path(__file__).with_name("mat_decal_label.png")      # 800 x 400 px, round corners in its alpha


def parcel():
    box = s3d.box("parcel", 160, 110, 70)
    s3d.fillet(box, 3)
    s3d.material(box, "plastic", color="#b08a5c", roughness=0.85)
    label = s3d.decal("label", LABEL, 80)                     # 80 mm across, 40 mm up
    s3d.at(label, on=box.face("+Z"), x=-25, y=12, z=0.1)       # a hair above the lid
    return s3d.group("parcel", box, label)
