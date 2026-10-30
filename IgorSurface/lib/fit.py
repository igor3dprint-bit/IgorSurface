"""Primitive fitting in pure Python (Fusion's Python ships without numpy).

Points are (x, y, z) tuples, normals unit tuples. Units are whatever the caller uses.
Every fit returns a Model with .dist(p) (signed distance) and .normal(p), plus rms/max.
"""
import math

# ---------- small linear algebra ----------

def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def add(a, b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def mul(a, s): return (a[0]*s, a[1]*s, a[2]*s)
def dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    n = norm(a)
    return (a[0]/n, a[1]/n, a[2]/n) if n > 1e-300 else (0.0, 0.0, 1.0)

def mean(pts):
    n = len(pts)
    return (sum(p[0] for p in pts)/n, sum(p[1] for p in pts)/n, sum(p[2] for p in pts)/n)

def perp_basis(a):
    """Two unit vectors orthogonal to a and to each other."""
    h = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = unit(cross(a, h))
    return u, cross(a, u)

def cov(vecs, center=None):
    c = center or (0.0, 0.0, 0.0)
    m = [[0.0]*3 for _ in range(3)]
    for v in vecs:
        d = (v[0]-c[0], v[1]-c[1], v[2]-c[2])
        for i in range(3):
            for j in range(i, 3):
                m[i][j] += d[i]*d[j]
    for i in range(3):
        for j in range(i):
            m[i][j] = m[j][i]
    return m

def eig_sym3(a):
    """Jacobi eigen-decomposition. Returns [(value, vector)] sorted ascending."""
    a = [row[:] for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(50):
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) < 1e-30:
            break
        th = 0.5*math.atan2(2*a[p][q], a[q][q]-a[p][p])
        c, s = math.cos(th), math.sin(th)
        for k in range(3):
            akp, akq = a[k][p], a[k][q]
            a[k][p], a[k][q] = c*akp - s*akq, s*akp + c*akq
        for k in range(3):
            apk, aqk = a[p][k], a[q][k]
            a[p][k], a[q][k] = c*apk - s*aqk, s*apk + c*aqk
        for k in range(3):
            vkp, vkq = v[k][p], v[k][q]
            v[k][p], v[k][q] = c*vkp - s*vkq, s*vkp + c*vkq
    return sorted(((a[i][i], (v[0][i], v[1][i], v[2][i])) for i in range(3)), key=lambda t: t[0])

def solve(m, b):
    """Gaussian elimination with partial pivoting. None if singular."""
    n = len(b)
    a = [list(m[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-18:
            return None
        a[c], a[p] = a[p], a[c]
        for r in range(c+1, n):
            f = a[r][c]/a[c][c]
            for k in range(c, n+1):
                a[r][k] -= f*a[c][k]
    x = [0.0]*n
    for r in range(n-1, -1, -1):
        x[r] = (a[r][n] - sum(a[r][k]*x[k] for k in range(r+1, n)))/a[r][r]
    return x

def lstsq(rows, rhs):
    """Normal equations for small systems."""
    n = len(rows[0])
    ata = [[0.0]*n for _ in range(n)]
    atb = [0.0]*n
    for r, y in zip(rows, rhs):
        for i in range(n):
            atb[i] += r[i]*y
            for j in range(n):
                ata[i][j] += r[i]*r[j]
    return solve(ata, atb)

# ---------- models ----------

class Model:
    kind = ''
    def stats(self, pts):
        d = [abs(self.dist(p)) for p in pts]
        self.rms = math.sqrt(sum(x*x for x in d)/len(d)) if d else float('inf')
        self.max = max(d) if d else float('inf')
        return self

class Plane(Model):
    kind = 'plane'
    def __init__(self, origin, n): self.origin, self.n = origin, unit(n)
    def dist(self, p): return dot(sub(p, self.origin), self.n)
    def normal(self, p): return self.n

class Sphere(Model):
    kind = 'sphere'
    def __init__(self, c, r): self.c, self.r = c, r
    def dist(self, p): return norm(sub(p, self.c)) - self.r
    def normal(self, p): return unit(sub(p, self.c))

class Cylinder(Model):
    kind = 'cylinder'
    def __init__(self, origin, axis, r): self.origin, self.axis, self.r = origin, unit(axis), r
    def radial(self, p):
        v = sub(p, self.origin)
        return sub(v, mul(self.axis, dot(v, self.axis)))
    def dist(self, p): return norm(self.radial(p)) - self.r
    def normal(self, p): return unit(self.radial(p))

class Cone(Model):
    """apex, axis pointing into the opening, half-angle in radians."""
    kind = 'cone'
    def __init__(self, apex, axis, ang): self.apex, self.axis, self.ang = apex, unit(axis), ang
    def dist(self, p):
        v = sub(p, self.apex); h = dot(v, self.axis)
        rr = norm(sub(v, mul(self.axis, h)))
        return rr*math.cos(self.ang) - h*math.sin(self.ang)
    def normal(self, p):
        v = sub(p, self.apex); h = dot(v, self.axis)
        rad = unit(sub(v, mul(self.axis, h)))
        return unit(sub(mul(rad, math.cos(self.ang)), mul(self.axis, math.sin(self.ang))))

# ---------- fits ----------

def fit_plane(pts, normals=None):
    c = mean(pts)
    n = eig_sym3(cov(pts, c))[0][1]
    return Plane(c, n).stats(pts)

def fit_sphere(pts, normals=None):
    # |p|^2 = 2c.p + (r^2 - |c|^2), linear in (cx, cy, cz, k); centered for conditioning
    o = mean(pts)
    q = [sub(p, o) for p in pts]
    x = lstsq([(2*p[0], 2*p[1], 2*p[2], 1.0) for p in q], [dot(p, p) for p in q])
    if x is None:
        return None
    c = (x[0], x[1], x[2])
    r2 = x[3] + dot(c, c)
    if r2 <= 0:
        return None
    return Sphere(add(c, o), math.sqrt(r2)).stats(pts)

def _circle_fit(pts, origin, axis):
    """Kasa circle fit of pts projected on the plane (origin, axis). Returns (center3d, r)."""
    u, v = perp_basis(axis)
    q = [(dot(sub(p, origin), u), dot(sub(p, origin), v)) for p in pts]
    x = lstsq([(2*a, 2*b, 1.0) for a, b in q], [a*a + b*b for a, b in q])
    if x is None:
        return None
    r2 = x[2] + x[0]**2 + x[1]**2
    if r2 <= 0:
        return None
    return add(origin, add(mul(u, x[0]), mul(v, x[1]))), math.sqrt(r2)

def fit_cylinder(pts, normals):
    # surface normals of a cylinder are all orthogonal to the axis
    axis = eig_sym3(cov(normals))[0][1]
    cr = _circle_fit(pts, mean(pts), axis)
    if cr is None:
        return None
    m = Cylinder(cr[0], axis, cr[1])
    # refine axis direction: Gauss-Newton on (axis tilt, center shift, r)
    m = _refine_cylinder(m, pts)
    return m.stats(pts)

def _refine_cylinder(m, pts, iters=5):
    for _ in range(iters):
        u, v = perp_basis(m.axis)
        rows, rhs = [], []
        for p in pts:
            d = m.radial(p); dn = norm(d)
            if dn < 1e-12:
                continue
            g = mul(d, 1/dn)
            h = dot(sub(p, m.origin), m.axis)
            # params: shift origin along u,v (a,b), tilt axis toward u,v (c,e), radius (f)
            rows.append((-dot(g, u), -dot(g, v), -h*dot(g, u), -h*dot(g, v), -1.0))
            rhs.append(-(dn - m.r))
        x = lstsq(rows, rhs)
        if x is None:
            break
        o = add(m.origin, add(mul(u, x[0]), mul(v, x[1])))
        ax = unit(add(m.axis, add(mul(u, x[2]), mul(v, x[3]))))
        m = Cylinder(o, ax, m.r + x[4])
        if max(abs(t) for t in x) < 1e-12:
            break
    return m

def fit_cone_faces(face_pts, face_normals, pts):
    """face_pts/face_normals: a point on each facet + its normal. pts: vertices for stats.
    Cone normals make a constant angle with the axis (axis = least-variance direction of the
    centered normals) and every tangent plane passes through the apex."""
    axis = eig_sym3(cov(face_normals, mean(face_normals)))[0][1]
    apex = lstsq(face_normals, [dot(n, p) for n, p in zip(face_normals, face_pts)])
    if apex is None:
        return None
    apex = tuple(apex)
    # orient axis toward the points
    if dot(sub(mean(pts), apex), axis) < 0:
        axis = mul(axis, -1)
    angs = []
    for p in pts:
        w = sub(p, apex); h = dot(w, axis)
        angs.append(math.atan2(norm(sub(w, mul(axis, h))), h))
    ang = sum(angs)/len(angs)
    if not (0.001 < ang < math.pi/2 - 0.001):
        return None
    return Cone(apex, axis, ang).stats(pts)

KINDS = ('plane', 'cylinder', 'sphere', 'cone')

def fit(kind, pts, face_pts, face_normals):
    """kind in KINDS or 'auto'. pts = region vertices, face_* = per-triangle centroid/normal."""
    if kind == 'plane':
        return fit_plane(pts)
    if kind == 'sphere':
        return fit_sphere(pts)
    if kind == 'cylinder':
        return fit_cylinder(pts, face_normals)
    if kind == 'cone':
        return fit_cone_faces(face_pts, face_normals, pts)
    return fit_auto(pts, face_pts, face_normals)

def fit_auto(pts, face_pts, face_normals, tol=None):
    """Simplest model whose rms is within ~tol (or 1.5x the best rms) wins."""
    cands = [m for m in (fit(k, pts, face_pts, face_normals) for k in KINDS) if m is not None]
    if not cands:
        return None
    best = min(m.rms for m in cands)
    size = max(norm(sub(p, pts[0])) for p in pts) or 1.0
    floor = max(best*1.5, size*1e-6, tol or 0.0)
    for m in cands:  # KINDS order = simplest first
        if m.rms <= floor:
            # a cone with tiny angle is a cylinder, one with ~90 deg is a plane: already caught by order
            return m
    return min(cands, key=lambda m: m.rms)
