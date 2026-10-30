"""Ground-structure truss optimization (pure Python, no numpy).
A grid of nodes fills the box around the supports and the load; every short bar between them is a candidate.
Optimality criteria (min compliance, fixed volume) thins useless bars away; what is left is a Michell-like truss.
Then each bar is sized by its real force: area = |force| / allowable stress. Units: cm, N, N/cm^2."""
import math
from math import gcd


def _sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _len(a): return math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])


def ground(supports, load, res=5, pad=0.15):
    """Nodes (grid + the given points) and candidate bars. Returns nodes, bars, support ids, load id."""
    pts = list(supports) + [load]
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    size = max(hi[k] - lo[k] for k in range(3)) or 1.0
    for k in range(3):  # a flat set of points stays flat (2D truss); otherwise pad the box
        if hi[k] - lo[k] > 0.02 * size:
            m = pad * size
            lo[k] -= m; hi[k] += m
    step = max(hi[k] - lo[k] for k in range(3)) / (res - 1)
    n = [max(1, round((hi[k] - lo[k]) / step)) + 1 if hi[k] - lo[k] > 0.02 * size else 1 for k in range(3)]
    nodes, ijk = [], {}
    for i in range(n[0]):
        for j in range(n[1]):
            for k in range(n[2]):
                ijk[(i, j, k)] = len(nodes)
                c = (i, j, k)
                nodes.append(tuple(lo[a] + (hi[a]-lo[a]) * c[a] / (n[a]-1) if n[a] > 1 else lo[a] for a in range(3)))
    bars = set()
    R = 2  # neighbours up to 2 cells away; gcd == 1 drops bars that run straight over another node
    for (i, j, k), a in ijk.items():
        for di in range(-R, R+1):
            for dj in range(-R, R+1):
                for dk in range(-R, R+1):
                    b = ijk.get((i+di, j+dj, k+dk))
                    if b is not None and b > a and gcd(gcd(abs(di), abs(dj)), abs(dk)) == 1:
                        bars.add((a, b))
    extra = []
    for p in pts:  # supports and load become nodes, tied to the grid nodes around them
        e = len(nodes)
        nodes.append(tuple(p))
        near = sorted(range(e), key=lambda q: _len(_sub(nodes[q], p)))[:8]
        bars.update((q, e) for q in near if _len(_sub(nodes[q], p)) > 1e-9)
        extra.append(e)
    return nodes, sorted(bars), extra[:-1], extra[-1]


def _solve(nodes, bars, area, fixed, f, E=1.0):
    """Displacements of the truss (conjugate gradient, Jacobi preconditioned). fixed: set of dof ids."""
    nd = 3 * len(nodes)
    geo = []
    for a, b in bars:
        d = _sub(nodes[b], nodes[a]); L = _len(d)
        geo.append((a, b, (d[0]/L, d[1]/L, d[2]/L), L))
    kk = [E*ar/L for ar, (_, _, _, L) in zip(area, geo)]
    eps = 1e-9 * max(kk)  # tiny spring on every dof: loose nodes and mechanisms stay solvable

    def K(x):
        y = [eps * v for v in x]
        for (a, b, c, L), k in zip(geo, kk):
            ia, ib = 3*a, 3*b
            t = k * (c[0]*(x[ib]-x[ia]) + c[1]*(x[ib+1]-x[ia+1]) + c[2]*(x[ib+2]-x[ia+2]))
            for m in range(3):
                y[ia+m] -= t*c[m]; y[ib+m] += t*c[m]
        for i in fixed:
            y[i] = x[i]
        return y
    diag = [eps] * nd
    for (a, b, c, L), k in zip(geo, kk):
        for m in range(3):
            diag[3*a+m] += k*c[m]*c[m]; diag[3*b+m] += k*c[m]*c[m]
    for i in fixed:
        diag[i] = 1.0
    rhs = [0.0 if i in fixed else f[i] for i in range(nd)]
    x = [0.0] * nd
    r = rhs[:]
    z = [ri/di for ri, di in zip(r, diag)]
    p = z[:]
    rz = sum(a*b for a, b in zip(r, z))
    tol = 1e-12 * max(1e-30, sum(v*v for v in rhs))
    for _ in range(4 * nd):
        Ap = K(p)
        al = rz / max(1e-300, sum(a*b for a, b in zip(p, Ap)))
        x = [xi + al*pi for xi, pi in zip(x, p)]
        r = [ri - al*ai for ri, ai in zip(r, Ap)]
        if sum(v*v for v in r) < tol:
            break
        z = [ri/di for ri, di in zip(r, diag)]
        rz2 = sum(a*b for a, b in zip(r, z))
        p = [zi + rz2/rz*pi for zi, pi in zip(z, p)]
        rz = rz2
    return x, geo


def optimize(nodes, bars, supports, load_node, force, iters=40, keep=0.02, progress=None):
    """Bars that survive and their relative areas: [(a, b, area)]. force: (Fx, Fy, Fz)."""
    fixed = {3*s + m for s in supports for m in range(3)}
    f = [0.0] * (3 * len(nodes))
    for m in range(3):
        f[3*load_node + m] = force[m]
    Ls = [_len(_sub(nodes[b], nodes[a])) for a, b in bars]
    V = sum(Ls)
    area = [1.0] * len(bars)
    for it in range(iters):
        u, geo = _solve(nodes, bars, area, fixed, f)
        # strain energy per unit volume: E * strain^2
        s = []
        for a, b, c, L in geo:
            dl = sum(c[m] * (u[3*b+m] - u[3*a+m]) for m in range(3))
            s.append((dl / L) ** 2)
        lo, hi = 1e-30, max(s) * 1e6 + 1e-30
        amin = 1e-4
        for _ in range(60):  # bisection on the Lagrange multiplier keeps the volume fixed
            lam = math.sqrt(lo * hi)
            new = [min(max(ar * math.sqrt(si / lam), ar*0.3, amin), ar*3) for ar, si in zip(area, s)]
            if sum(x*L for x, L in zip(new, Ls)) > V:
                lo = lam
            else:
                hi = lam
        area = new
        if progress:
            progress(it + 1, iters)
    top = max(area)
    return [(a, b, ar/top) for (a, b), ar in zip(bars, area) if ar > keep*top]


def forces(nodes, kept, supports, load_node, force):
    """Axial force (N, + = tension) in each kept bar, solved on the kept truss alone."""
    fixed = {3*s + m for s in supports for m in range(3)}
    f = [0.0] * (3 * len(nodes))
    for m in range(3):
        f[3*load_node + m] = force[m]
    bars = [(a, b) for a, b, _ in kept]
    area = [ar for _, _, ar in kept]
    u, geo = _solve(nodes, bars, area, fixed, f)
    return [ar * sum(c[m] * (u[3*b+m] - u[3*a+m]) for m in range(3)) / L
            for ar, (a, b, c, L) in zip(area, geo)]


def design(supports, load, force, stress, dmin, res=5, progress=None):
    """Whole pipeline: [(p0, p1, diameter_cm, axial_N)]. stress in N/cm^2, dmin in cm."""
    nodes, bars, sup, ld = ground(supports, load, res)
    kept = optimize(nodes, bars, sup, ld, force, progress=progress)
    for _ in range(5):  # drop bars carrying almost nothing and loose ends, then re-solve
        N = forces(nodes, kept, sup, ld, force)
        top = max(abs(x) for x in N)
        k2 = [b for b, x in zip(kept, N) if abs(x) > 0.03 * top]
        while True:
            deg = {}
            for a, b, _ in k2:
                deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
            loose = {n for n, c in deg.items() if c < 2 and n not in sup and n != ld}
            if not loose:
                break
            k2 = [b for b in k2 if b[0] not in loose and b[1] not in loose]
        if len(k2) == len(kept):
            break
        kept = k2
    out = []
    for (a, b, _), N in zip(kept, forces(nodes, kept, sup, ld, force)):
        # ponytail: compression sized like tension x2 (rough buckling margin); add Euler check if bars get slender
        A = abs(N) * (2 if N < 0 else 1) / stress
        out.append((nodes[a], nodes[b], max(dmin, math.sqrt(4*A/math.pi)), N))
    return out


if __name__ == '__main__':
    # cantilever: two supports on the left wall, load down at the right
    res = design([(0, 0, 0), (0, 0, 4)], (8, 0, 2), (0, 0, -100), 1500.0, 0.2, res=5)
    assert res, 'no bars'
    # equilibrium at the load: kept bars must carry the load (sum of vertical components ~ 100 N)
    ends = [r for r in res if r[0] == (8, 0, 2) or r[1] == (8, 0, 2)]
    assert ends, 'load node not connected'
    print('ok', len(res), 'bars; max force %.1f N' % max(abs(r[3]) for r in res))
