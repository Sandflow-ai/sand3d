# Per-face colour, broad weathering and geometry cost

Colour resolution is the faces': freckles vanish on coarse meshes. Prefer broad gradients,
height or moisture bands, directional grime and seeded noise at visible scales. Never refine or
displace a mesh only to carry finer colour; relief is justified when it changes the silhouette or the
material's structure.

```python
import numpy as np

def weathered(x, y, z):
    t = np.clip((z + 20) / 120, 0, 1)
    low = np.array([.12, .08, .04])
    high = np.array([.48, .38, .22])
    blend = np.interp(t, [0, .4, 1], [0, .2, 1])
    rgb = low + blend[:, None] * (high - low)
    return np.where((z < -10)[:, None], low, rgb)

# s3d.material(part, "bark", color=weathered)
```
