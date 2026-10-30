import sys, time, math; sys.path.insert(0, 'IgorSurface')
from lib.region import Mesh, detect
idx, coords, key = [], [], {}
for line in open('tests/block_hole.stl'):
    s = line.split()
    if s and s[0] == 'vertex':
        p = tuple(round(float(x)/10, 7) for x in s[1:])  # mm -> cm like Fusion
        if p not in key: key[p] = len(key); coords += p
        idx.append(key[p])
m = Mesh(coords, idx)
for name, click in (('top', (2.5, 0.3, 1.0)), ('hole', (2.0, 1.0, 0.5)), ('side', (3.0, 1.0, 0.5))):
    t = time.perf_counter(); mod, reg = detect(m, [m.nearest_tri(click)])
    extra = ' D=%.4f mm' % (mod.r*20) if mod.kind == 'cylinder' else ''
    print(name, mod.kind, len(reg), 'tris rms=%.2e mm%s %.0f ms' % (mod.rms*10, extra, (time.perf_counter()-t)*1e3))
# closest point must be exact on big flat triangles (side face y=0)
import random
rnd = random.Random(3)
for _ in range(200):
    q = (rnd.uniform(0.1, 2.9), rnd.uniform(-0.3, -0.01), rnd.uniform(0.05, 0.95))
    p, t = m.closest(q)
    assert abs(p[1]) < 1e-9 and abs(p[0]-q[0]) < 1e-9 and abs(p[2]-q[2]) < 1e-9, (q, p)
print('closest ok')
segs, corners = m.sharp()
print('sharp segs', len(segs), 'corners', len(corners))
assert len(corners) == 8, corners  # block has 8 crisp corners; hole rims are loops (degree 2)
from lib.region import snap_point
assert snap_point((0.01, 0.02, 0.99), 0.15, corners, segs) == (0.0, 0.0, 1.0)
q = snap_point((1.5, 0.05, 0.98), 0.15, corners, segs); assert abs(q[1]) < 1e-9 and abs(q[2]-1) < 1e-9, q
print('snap ok')
from lib.region import deviation, heat
d = deviation(m, [(1.0, 1.0, 1.02), (2.5, 0.5, 0.97), (0.5, 0.5, 1.0)])
assert abs(d[0] - 0.02) < 1e-9 and abs(d[1] + 0.03) < 1e-9 and abs(d[2]) < 1e-9, d
assert heat(0.0, .01, .1)[1] == 200 and heat(.2, .01, .1)[:3] == (255, 0, 0) and heat(-.2, .01, .1)[:3] == (0, 0, 255)
print('deviation ok')
from lib.region import closest_on_tri, Mesh as M2
assert closest_on_tri((0, 1, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0)) == (0, 0, 0)  # collinear sliver
assert closest_on_tri((5, 1, 0), (1, 0, 0), (1, 0, 0), (1, 0, 0)) == (1, 0, 0)  # all vertices equal
# one huge triangle among tiny ones: still found
tiny = [c for i in range(300) for c in (i*0.01, 5, 0, i*0.01+0.01, 5, 0, i*0.01, 5.01, 0)]
mm = M2(tiny + [0, 0, 1, 100, 0, 1, 0, 100, 1], list(range(903)))
q, t = mm.closest((60, 30, 1.5)); assert t == 300 and abs(q[2] - 1) < 1e-9, (q, t)
print('degenerate + big triangle ok')
