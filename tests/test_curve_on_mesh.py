import sys, math; sys.path.insert(0, 'IgorSurface'); sys.path.insert(0, 'tests')
from lib.region import Mesh, snap_curve, surface_path
from lib.fit import norm, sub
import test_fillet as F  # reuses the L-shaped extrusion
m = F.extrude(F.fillet_prof)
def on_mesh(pts):
    return max(norm(sub(p, m.closest(p)[0])) for p in pts)
# floor -> wall across the fillet: every point on the surface, path climbs over the round
p0, p1 = (-0.5, 0.33, 0.0), (F.R, 0.62, 0.7)
c = snap_curve(m, p0, p1)
assert c[0] == p0 and c[-1] == p1 and on_mesh(c) < 1e-6, on_mesh(c)
assert any(0 < p[0] < F.R and 0 < p[2] < F.R for p in c), c  # passes over the fillet
L = sum(norm(sub(c[i+1], c[i])) for i in range(len(c)-1))
print('fillet path pts', len(c), 'len %.3f' % L)
# thin plate 0.1 thick: line on top must stay on top (old closest-point could jump to the bottom)
s = 10; co = []; ix = []
def grid(z, flip):
    base = len(co)//3
    for j in range(s+1):
        for i in range(s+1): co.extend((i*0.2, j*0.2, z))
    for j in range(s):
        for i in range(s):
            a = base+j*(s+1)+i; b, d, e = a+1, a+s+1, a+s+2
            ix.extend((a, e, b, a, d, e) if flip else (a, b, e, a, e, d))
grid(0.1, False); grid(0.0, True)
pm = Mesh(co, ix)
c = snap_curve(pm, (0.1, 0.1, 0.1), (1.9, 1.7, 0.1))
assert all(abs(p[2]-0.1) < 1e-9 for p in c), c
print('thin plate ok, pts', len(c))
print('curve on mesh ok')
# noisy scan: the faired line stays on the mesh but doesn't copy the noise (smooth turn angles)
from lib.region import chains
mn = F.extrude(F.fillet_prof, noise=0.002)
c = snap_curve(mn, (-0.5, 0.33, 0.0), (F.R, 0.62, 0.7))
assert max(norm(sub(p, mn.closest(p)[0])) for p in c[1:-1]) < 1e-6  # ends are the clicked nodes
from lib.fit import dot, unit
turn = max(math.degrees(math.acos(max(-1, min(1, dot(unit(sub(c[i], c[i-1])), unit(sub(c[i+1], c[i]))))))) for i in range(1, len(c)-1))
print('noisy pts', len(c), 'max turn %.1f deg' % turn)
dev = max(norm(sub(p, m.closest(p)[0])) for p in c[1:-1])  # vs the clean part
print('off clean part %.4f cm' % dev); assert dev < 0.002 and len(c) < 15, (dev, len(c))
# runs: square loop + a tail from a junction
r = chains([(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (4, 5)])
assert sorted(map(len, r)) == [3, 5] and any(x[0] == x[-1] for x in r), r
r = chains([(0, 1), (1, 2), (2, 0)]); assert len(r) == 1 and r[0][0] == r[0][-1], r
print('smooth + chains ok')
