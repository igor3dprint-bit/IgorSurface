import sys, math, random; sys.path.insert(0, 'IgorSurface')
from lib.region import Mesh, detect, robust_fit
# 1) plane z=0 with 8 spikes: robust fit keeps normal (0,0,1)
pts = [(x*0.1, y*0.1, 0.0) for x in range(11) for y in range(11)] + [(0.5, 0.5, 1.0)]*8
m = robust_fit('plane', pts, [], [], 0.005)
assert abs(abs(m.n[2]) - 1) < 1e-6 and m.rms < 1e-9, (m.n, m.rms)
# 2) noisy grid mesh: flat plate vs wavy plate (wave 0.5 mm >> tol 0.05 mm)
def plate(f):
    N = 20; c = []; idx = []
    for j in range(N+1):
        for i in range(N+1):
            x, y = i*0.1, j*0.1; c += [x, y, f(x, y)]
    for j in range(N):
        for i in range(N):
            a = j*(N+1)+i; b, d, e = a+1, a+N+1, a+N+2
            idx += [a, b, e, a, e, d]
    return Mesh(c, idx)
rnd = random.Random(1)
flat = plate(lambda x, y: rnd.uniform(-0.002, 0.002))
mod, reg = detect(flat, [flat.nearest_tri((1, 1, 0))], 'auto', 0.005, strict=True)
assert mod and mod.kind == 'plane' and len(reg) > 700, (mod, len(reg))
wavy = plate(lambda x, y: 0.05*math.sin(3*x)*math.sin(3*y))
mod, reg = detect(wavy, [wavy.nearest_tri((0.5, 0.5, 0))], 'auto', 0.005, strict=True)
print('wavy ->', mod and mod.kind, len(reg))
print('robust ok')
