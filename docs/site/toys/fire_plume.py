import numpy as np
import sand3d as s3d


def campfire(seed=0, ring=115, h=420):
    stones = [s3d.at(s3d.displace(s3d.sphere("stone", 45), 4, 15, seed=i), on=f) for i, f in enumerate(s3d.ring(9, ring))]
    log_length, log_d, log_z, angular_span = 140, 22, 12, 120
    log = s3d.wire("log", [(-log_length / 2, 0, 0), (log_length / 2, 0, 0)], d=log_d)
    s3d.material(log, "bark", color="#2b2420")
    logs = s3d.at(log, on=s3d.ring(3, 0, angle=angular_span).offset(log_z))
    plume = lambda x, y, z: np.hypot(x - z * z / 3000, y) - (20 + z / 8) * (1 + .35 * s3d.noise(x / 40, y / 40, z / 40, seed=seed))
    smoke = s3d.at(s3d.field("smoke", (320, 240, h), plume, cell=6), z=25)
    s3d.material(stones, "rock", color="#3f3b36")
    s3d.material(smoke, "smoke", scatter="#c8c8c8", scatter_distance=25)
    return s3d.assembly("campfire", stones, logs, smoke)
