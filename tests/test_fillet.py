import sys, math, random; sys.path.insert(0, 'IgorSurface')
from lib.region import Mesh, detect
def extrude(prof, L=1.0, M=10, noise=0.0, seed=2):
    """Profile [(x,z)] swept along y -> grid mesh."""
    rnd = random.Random(seed); c = []; idx = []; N = len(prof)
    for j in range(M+1):
        for x, z in prof:
            c += [x, j*L/M, z + rnd.uniform(-noise, noise)]
    for j in range(M):
        for i in range(N-1):
            a = j*N+i; b, d, e = a+1, a+N, a+N+1
            idx += [a, b, e, a, e, d]
    return Mesh(c, idx)
R = 0.3
fl = [(-1 + i*0.1, 0.0) for i in range(10)]                       # floor x -1..-0.1
arc = [(-R*math.sin(t), R - R*math.cos(t)) for t in [k*math.pi/2/8 for k in range(9)]]  # wrong side guard below
arc = [(R*math.sin(t) - 0.0, R - R*math.cos(t)) for t in [k*math.pi/2/8 for k in range(9)]]
wall = [(R, R + 0.1*k) for k in range(1, 10)]                       # wall x=R
fillet_prof = [(x - 0.0, z) for x, z in fl] + [(x, z) for x, z in arc] + wall
ch = [(0.0, 0.0), (0.2, 0.2)] + [(0.2, 0.2 + 0.1*k) for k in range(1, 10)]
chamfer_prof = fl + [(0.0 + 0.04*k, 0.04*k) for k in range(6)] + [(0.2, 0.2 + 0.1*k) for k in range(1, 10)]
for name, prof, clicks in (('fillet', fillet_prof, {'floor': (-0.5, .5, 0), 'fillet': (R*math.sin(.8), .5, R-R*math.cos(.8)), 'wall': (R, .5, .7)}),
                           ('chamfer', chamfer_prof, {'floor': (-0.5, .5, 0), 'chamfer': (0.1, .5, 0.1), 'wall': (0.2, .5, .7)})):
    for noise in (0.0, 0.002):
        m = extrude(prof, noise=noise)
        for k, p in clicks.items():
            mod, reg = detect(m, [m.nearest_tri(p)], 'auto', 0.005, strict=True)
            r = (' r=%.3f' % mod.r) if mod and hasattr(mod, 'r') else ''
            print('%-7s n=%.3f %-7s -> %-8s %4d/%d tris%s' % (name, noise, k, mod and mod.kind, len(reg), len(m.t), r))
# guard: fillet found as r=0.3 cylinder, floor/wall stay planes and don't swallow the fillet (160 tris)
m = extrude(fillet_prof, noise=0.002)
mod, reg = detect(m, [m.nearest_tri((R*math.sin(.8), .5, R-R*math.cos(.8)))], 'auto', 0.005, strict=True)
assert mod.kind == 'cylinder' and abs(mod.r - R) < 0.005 and len(reg) >= 150, (mod.kind, len(reg))
mod, reg = detect(m, [m.nearest_tri((-0.5, .5, 0))], 'auto', 0.005, strict=True)
assert mod.kind == 'plane' and len(reg) < 240, len(reg)
print('fillet ok')
