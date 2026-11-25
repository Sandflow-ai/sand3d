import sand3d as s3d


def seat():
    host = s3d.box("host", 90, 60, 25)
    insert = s3d.at(s3d.cylinder("insert", 38, 35), z=12)
    s3d.joint("lift", insert, s3d.local(host), kind="prismatic", range=(0, 60))
    s3d.pose(insert, 45)
    s3d.seat(host, insert)
    s3d.material(host, "oak")
    s3d.material(insert, "brass")
    return s3d.assembly("seat_at_rest", host, insert)
