import json, struct
from pathlib import Path

class Glb:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        size = struct.unpack_from('<I', raw, 12)[0]
        self.doc = json.loads(raw[20:20+size])
        self.binary = raw[28+size:]

    def rows(self, index):
        a = self.doc['accessors'][index]
        v = self.doc['bufferViews'][a['bufferView']]
        count = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        fmt = '<' + {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}[a['componentType']] * count
        offset = v.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = v.get('byteStride', struct.calcsize(fmt))
        return [struct.unpack_from(fmt, self.binary, offset+i*stride) for i in range(a['count'])]

    def positions(self):
        return [p for m in self.doc['meshes'] for prim in m['primitives']
                for p in self.rows(prim['attributes']['POSITION'])]

    def triangles(self):
        return sum(len(self.rows(p['indices']))//3 for m in self.doc['meshes'] for p in m['primitives'])
