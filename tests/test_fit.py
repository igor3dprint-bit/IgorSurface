"""Runs outside Fusion: python test_fit.py"""
import math, random, sys, time
sys.path.insert(0, 'IgorSurface/lib')
from fit import fit, sub, cross, unit, mean, dot, norm

def grid(f, nu, nv, noise, rnd):
    """Triangulate param surface f(u,v)->point on [0,1]^2, return (verts, face_pts, face_normals)."""
    P = [[tuple(c + rnd.gauss(0, noise) for c in f(i/nu, j/nv)) for j in range(nv+1)] for i in range(nu+1)]
    verts = [p for row in P for p in row]
    fp, fn = [], []
    for i in range(nu):
        for j in range(nv):
            for a, b, c in ((P[i][j], P[i+1][j], P[i+1][j+1]), (P[i][j], P[i+1][j+1], P[i][j+1])):
                fp.append(mean((a, b, c))); fn.append(unit(cross(sub(b, a), sub(c, a))))
    return verts, fp, fn

def check(name, kind, f, expect, noise, tol, n=24):
    rnd = random.Random(1)
    v, fp, fn = grid(f, n, n, noise, rnd)
    t = time.perf_counter()
    m = fit(kind, v, fp, fn)
    dt = time.perf_counter() - t
    assert m is not None, name
    assert m.kind == expect[0], (name, m.kind)
    for got, want in expect[1](m):
        assert abs(got - want) < tol, (name, got, want)
    print('ok %-26s %-8s rms=%.2e  %.0f ms' % (name, m.kind, m.rms, dt*1e3))

R = 5.0
ax = unit((0.3, -0.2, 1.0))
u0 = unit(cross(ax, (1, 0, 0))); v0 = cross(ax, u0)
C = (1.0, 2.0, 3.0)
def on_cyl(u, v, r=R, span=1.0):
    a = 2*math.pi*u*span
    return tuple(C[k] + r*(math.cos(a)*u0[k] + math.sin(a)*v0[k]) + 20*v*ax[k] for k in range(3))
def on_sph(u, v):
    a, b = 2*math.pi*u, 0.2 + 2.6*v
    return (C[0] + R*math.sin(b)*math.cos(a), C[1] + R*math.sin(b)*math.sin(a), C[2] + R*math.cos(b))
def on_plane(u, v):
    return tuple(C[k] + 30*u*u0[k] + 10*v*v0[k] for k in range(3))
def on_cone(u, v, ang=math.radians(20)):
    a, h = 2*math.pi*u, 5 + 10*v
    return tuple(C[k] + h*ax[k] + h*math.tan(ang)*(math.cos(a)*u0[k] + math.sin(a)*v0[k]) for k in range(3))

r_ = lambda m: [(m.r, R)]
for noise, tol in ((0.0, 1e-6), (0.01, 0.02)):
    tag = ' noise=%g' % noise
    for kind in ('auto', None):
        check('plane' + tag, kind or 'plane', on_plane, ('plane', lambda m: [(abs(dot(m.n, ax)), 1.0)]), noise, tol)
        check('cylinder' + tag, kind or 'cylinder', on_cyl, ('cylinder', r_), noise, tol)
        check('cyl 90deg arc' + tag, kind or 'cylinder', lambda u, v: on_cyl(u, v, span=0.25), ('cylinder', r_), noise, tol*3)
        check('sphere' + tag, kind or 'sphere', on_sph, ('sphere', lambda m: [(m.r, R), (norm(sub(m.c, C)), 0.0)]), noise, tol)
        check('cone' + tag, kind or 'cone', on_cone, ('cone', lambda m: [(math.degrees(m.ang), 20.0), (norm(sub(m.apex, C)), 0.0)]), noise, tol*10)

# diameter on a coarse clean tessellated hole must be exact (vertices lie on the true circle)
check('hole D10 96 segs', 'auto', lambda u, v: on_cyl(u, v, r=5.0), ('cylinder', lambda m: [(2*m.r, 10.0)]), 0.0, 1e-6, n=96)

# speed: ~100k triangles
rnd = random.Random(2)
v, fp, fn = grid(on_cyl, 224, 224, 0.001, rnd)
t = time.perf_counter(); m = fit('auto', v, fp, fn)
print('speed: %d tris auto-fit %.2f s -> %s' % (len(fn), time.perf_counter()-t, m.kind))
print('ALL OK')
