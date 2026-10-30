import sys, math, os, random, tempfile, struct; sys.path.insert(0, 'IgorSurface')
from lib.region import Mesh
from lib.scan import frame, apply, symmetry, read_ply, write_stl
from lib.fit import unit, cross, dot
# block mesh, then rotated+shifted like a raw scan
idx, coords, key = [], [], {}
for line in open('tests/block_hole.stl'):
    s = line.split()
    if s and s[0] == 'vertex':
        p = tuple(round(float(x)/10, 7) for x in s[1:])
        if p not in key: key[p] = len(key); coords += p
        idx.append(key[p])
ax = unit((0.3, 0.5, 0.8)); a = 0.9
def rot(p):
    c, s = math.cos(a), math.sin(a)
    k = ax; d = dot(k, p); x = cross(k, p)
    return tuple(p[i]*c + x[i]*s + k[i]*d*(1-c) + (5, -3, 2)[i] for i in range(3))
V = [rot(coords[i:i+3]) for i in range(0, len(coords), 3)]
m = Mesh([c for p in V for c in p], idx)
# align: floor = rotated bottom face, x hint = rotated +X
floor_o, floor_n = rot((0, 0, 0)), unit(tuple(rot((0, 0, 1))[i] - rot((0, 0, 0))[i] for i in range(3)))
xh = tuple(rot((1, 0, 0))[i] - rot((0, 0, 0))[i] for i in range(3))
R, t = frame(floor_o, floor_n, V, xh)
A = [apply(R, t, p) for p in V]
zs = [p[2] for p in A]; xs = [p[0] for p in A]; ys = [p[1] for p in A]
assert abs(min(zs)) < 1e-9 and abs(max(zs) - 1) < 1e-9, (min(zs), max(zs))
assert abs(max(xs) - 1.5) < 1e-9 and abs(min(xs) + 1.5) < 1e-9 and abs(max(ys) - 1) < 1e-9, (min(xs), max(xs), max(ys))
print('align ok')
o, n, rms = symmetry(m)
print('symmetry rms %.2e' % rms); assert rms < 1e-3
# PLY ascii + binary round trip
tmp = tempfile.mkdtemp()
quad = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
with open(os.path.join(tmp, 'a.ply'), 'w') as f:
    f.write('ply\nformat ascii 1.0\nelement vertex 4\nproperty float x\nproperty float y\nproperty float z\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n')
    f.write(''.join('%g %g %g\n' % p for p in quad) + '4 0 1 2 3\n')
with open(os.path.join(tmp, 'b.ply'), 'wb') as f:
    f.write(b'ply\nformat binary_little_endian 1.0\nelement vertex 4\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n')
    for p in quad: f.write(struct.pack('<3fB', *p, 200))
    f.write(struct.pack('<B4i', 4, 0, 1, 2, 3))
for nm in ('a.ply', 'b.ply'):
    v, fc = read_ply(os.path.join(tmp, nm)); assert v == quad and fc == [(0, 1, 2), (0, 2, 3)], (nm, v, fc)
write_stl(os.path.join(tmp, 'o.stl'), v, fc); assert os.path.getsize(os.path.join(tmp, 'o.stl')) == 84 + 50*2
print('ply/stl ok')
