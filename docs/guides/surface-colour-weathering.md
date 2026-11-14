# Per-vertex colour, broad weathering and geometry cost.

material(ob, kind, color=callback) evaluates color(x,y,z[,n[,u]]) at vertices; coordinates are local, n is the normal and u is available surface parameterization. Return RGB/RGBA colours. Vertex colour resolution follows existing vertices: tiny freckles disappear on coarse meshes. Prefer broad gradients, height/moisture bands, directional grime and seeded noise at visible scales. Detail costs faces: displacing a mesh solely to carry finer colour increases build cost. Do not refine geometry solely for colour; use broad readable weathering first. Geometry relief is justified when it changes silhouette or material structure.


### Vectorized surface colour callbacks

`color=f(x,y,z[,n[,u]])` is evaluated at polygon centres in the mesh's local
frame, before placement. For a batch of k polygons, x, y and z are float64
NumPy arrays of shape (k,), n is an array of shape (3,k) (use n[2], not
n[:,2]), and lengthwise u has shape (k,). Return an ndarray of shape (k,3),
finite sRGB values in [0,1]. The implementation first probes a batch of at most
8 polygons, then calls the same function on the complete batch. One vectorized
path is sufficient; do not duplicate it with an isinstance/scalar branch.
There is a compatibility fallback: if the probe raises or does not return an
ndarray of shape (k,3), the library calls the callback once per polygon with
scalar x/y/z, a normal tuple and scalar u. A correctly shaped vectorized callback
never needs that fallback. Keep callbacks deterministic and free of side effects.

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

The colour is surface reflectance, not illumination. Do not bake a light direction,
highlight or cast shadow into RGB via normals. Use normals for an authored surface
property (e.g. deposited dust), not fake lighting. The review renderer supplies
fixed lighting; emission adds visible colour without lighting neighbours. Cycles
uses actual lights, emission and volume nodes and can show different appearance.
