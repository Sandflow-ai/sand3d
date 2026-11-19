import sand3d as s3d


def gate(w=750, h=1200, post=100):
    l_post = s3d.at(s3d.box("post", post, post, h + 300), x=-w - post / 2)
    r_post = s3d.transform(s3d.copy(l_post), mirror="x")
    board = s3d.at(s3d.box("board", w, 40, h), x=-w / 2, z=150)                    # from the post to x = 0
    handle = s3d.at(s3d.cylinder("handle", 20, 60), on=s3d.bbox(board, "+Y").move(x=60 - w / 2))  # near x = 0
    leaf = s3d.group("leaf", board, handle)                                        # the handle moves with it
    s3d.joint("hinge", leaf, s3d.bbox(l_post, "+X+Y"), axis="+Z", range=(0, 90))   # the post's edge it opens toward: +X turns toward +Y
    twin = s3d.transform(s3d.copy(leaf), mirror="x")                               # its image, hinged at x = +w: opens toward +Y too
    gate = s3d.assembly("gate", l_post, r_post, leaf, twin)
    s3d.pose(leaf, 60)   # shows the swing; a program returns at rest
    return gate
