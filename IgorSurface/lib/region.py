"""Mesh topology + region growing from clicked seeds. Pure Python, no Fusion imports."""
import math
from collections import deque
from .fit import sub, cross, unit, dot, norm, fit, mean

class Mesh:
    def __init__(self, coords, tri_idx):
        """coords: flat xyz list, tri_idx: flat triangle node indices."""
        self.v = [(coords[i], coords[i+1], coords[i+2]) for i in range(0, len(coords), 3)]
        self.t = [(tri_idx[i], tri_idx[i+1], tri_idx[i+2]) for i in range(0, len(tri_idx), 3)]
        self.cen, self.nrm = [], []
        for a, b, c in self.t:
            pa, pb, pc = self.v[a], self.v[b], self.v[c]
            self.cen.append(((pa[0]+pb[0]+pc[0])/3, (pa[1]+pb[1]+pc[1])/3, (pa[2]+pb[2]+pc[2])/3))
            self.nrm.append(unit(cross(sub(pb, pa), sub(pc, pa))))
        edges = {}
        for ti, (a, b, c) in enumerate(self.t):
            for e in ((a, b), (b, c), (c, a)):
                edges.setdefault((min(e), max(e)), []).append(ti)
        self.edges = edges
        self._sharp = None
        self.nb = [[] for _ in self.t]
        for tris in edges.values():
            for x in tris:
                for y in tris:
                    if x != y:
                        self.nb[x].append(y)

        # uniform grid; each triangle sits in every cell its bounding box touches (big flat triangles too)
        el = [norm(sub(self.v[a], self.v[b])) for a, b, _ in self.t[:2000]]
        self.cell = max(sum(el)/len(el), 1e-6) if el else 1.0
        self.grid = {}
        self.big = []  # triangles covering too many cells: always candidates
        for i, (a, b, c) in enumerate(self.t):
            pa, pb, pc = self.v[a], self.v[b], self.v[c]
            lo = self._key((min(pa[0], pb[0], pc[0]), min(pa[1], pb[1], pc[1]), min(pa[2], pb[2], pc[2])))
            hi = self._key((max(pa[0], pb[0], pc[0]), max(pa[1], pb[1], pc[1]), max(pa[2], pb[2], pc[2])))
            if (hi[0]-lo[0]+1)*(hi[1]-lo[1]+1)*(hi[2]-lo[2]+1) > 4096:
                self.big.append(i)
                continue
            for x in range(lo[0], hi[0]+1):
                for y in range(lo[1], hi[1]+1):
                    for z in range(lo[2], hi[2]+1):
                        self.grid.setdefault((x, y, z), []).append(i)

    def _key(self, p):
        return (int(math.floor(p[0]/self.cell)), int(math.floor(p[1]/self.cell)), int(math.floor(p[2]/self.cell)))

    def _near(self, p):
        """Triangles in the cells around p; the ring widens until something is found, then one more ring."""
        k = self._key(p)
        for r in range(0, 64):
            out = {i for dx in range(-r, r+1) for dy in range(-r, r+1) for dz in range(-r, r+1)
                   for i in self.grid.get((k[0]+dx, k[1]+dy, k[2]+dz), ())}
            if out or (self.big and r > 2):
                return out | set(self.big) | {i for dx in range(-r-1, r+2) for dy in range(-r-1, r+2) for dz in range(-r-1, r+2)
                              for i in self.grid.get((k[0]+dx, k[1]+dy, k[2]+dz), ())}
        return range(len(self.t))

    def closest(self, p):
        """(point on mesh, triangle) closest to p."""
        best = None
        if not self.t:
            raise ValueError('malha sem triângulos')
        for t in self._near(p):
            q = closest_on_tri(p, *(self.v[i] for i in self.t[t]))
            d = (q[0]-p[0])**2 + (q[1]-p[1])**2 + (q[2]-p[2])**2
            if best is None or d < best[0]:
                best = (d, q, t)
        return best[1], best[2]

    def sharp(self, angle=math.radians(30)):
        """(segments, corner vertices) of the part's crisp edges: dihedral above angle or open border."""
        if self._sharp is None:
            c = math.cos(angle)
            segs = [e for e, tris in self.edges.items()
                    if len(tris) != 2 or dot(self.nrm[tris[0]], self.nrm[tris[1]]) < c]
            deg = {}
            for a, b in segs:
                deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
            # a corner is where 3+ crisp edges meet or a crisp line ends
            corners = [v for v, n in deg.items() if n != 2]
            self._sharp = ([(self.v[a], self.v[b]) for a, b in segs], [self.v[i] for i in corners])
        return self._sharp

    def nearest_tri(self, p):
        return self.closest(p)[1]

    def region_data(self, tris):
        vs = sorted({i for t in tris for i in self.t[t]})
        return [self.v[i] for i in vs], [self.cen[t] for t in tris], [self.nrm[t] for t in tris]

def closest_on_tri(p, a, b, c):
    """Closest point to p on triangle abc. Degenerate (sliver/repeated-vertex) triangles fall back to edges."""
    try:
        return _closest_on_tri(p, a, b, c)
    except ZeroDivisionError:
        cands = [closest_on_seg(p, a, b), closest_on_seg(p, b, c), closest_on_seg(p, c, a)]
        return min(cands, key=lambda q: norm(sub(q, p)))

def _closest_on_tri(p, a, b, c):
    """Ericson, Real-Time Collision Detection 5.1.5."""
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0: return a
    bp = sub(p, b); d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3: return b
    vc = d1*d4 - d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1/(d1-d3); return (a[0]+ab[0]*v, a[1]+ab[1]*v, a[2]+ab[2]*v)
    cp = sub(p, c); d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6: return c
    vb = d5*d2 - d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2/(d2-d6); return (a[0]+ac[0]*w, a[1]+ac[1]*w, a[2]+ac[2]*w)
    va = d3*d6 - d5*d4
    if va <= 0 and (d4-d3) >= 0 and (d5-d6) >= 0:
        w = (d4-d3)/((d4-d3)+(d5-d6)); return (b[0]+(c[0]-b[0])*w, b[1]+(c[1]-b[1])*w, b[2]+(c[2]-b[2])*w)
    den = 1/(va+vb+vc); v, w = vb*den, vc*den
    return (a[0]+ab[0]*v+ac[0]*w, a[1]+ab[1]*v+ac[1]*w, a[2]+ab[2]*v+ac[2]*w)

def closest_on_seg(p, a, b):
    ab = sub(b, a); l2 = dot(ab, ab)
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, dot(sub(p, a), ab)/l2))
    return (a[0]+ab[0]*t, a[1]+ab[1]*t, a[2]+ab[2]*t)

def snap_point(p, tol, verts, segs):
    """Nearest of verts within tol, else nearest point on segs within tol, else None."""
    best = min(((norm(sub(v, p)), v) for v in verts), default=None, key=lambda t: t[0])
    if best and best[0] <= tol:
        return best[1]
    best = min(((norm(sub(q, p)), q) for q in (closest_on_seg(p, a, b) for a, b in segs)), default=None, key=lambda t: t[0])
    return best[1] if best and best[0] <= tol else None

def surface_path(mesh, p0, p1, tol=0.01):  # 0.1 mm: keeps shape, drops scan noise wiggles
    """Path on the mesh from p0 to p1: walk the section by the plane through p0, p1 and their average normal,
    triangle to triangle, both ways round; the shorter walk that arrives wins. None if the walk can't connect."""
    t0, t1 = mesh.nearest_tri(p0), mesh.nearest_tri(p1)
    if t0 == t1:
        return [p0, p1]
    d = sub(p1, p0)
    nav = tuple(a + b for a, b in zip(mesh.nrm[t0], mesh.nrm[t1]))
    if norm(nav) < 1e-6:  # opposite faces of a thin wall
        nav = mesh.nrm[t0]
    pn = cross(d, nav)
    if norm(pn) < 1e-9 * (norm(d) or 1):
        return None
    pn = unit(pn)
    side = lambda i: dot(sub(mesh.v[i], p0), pn)
    budget = 4 * norm(d) + 10 * tol
    best = None
    for first in (0, 1):
        crossed = [e for e in ((a, b) for a, b in (mesh.t[t0][:2], mesh.t[t0][1:], (mesh.t[t0][2], mesh.t[t0][0])))
                   if (side(e[0]) >= 0) != (side(e[1]) >= 0)]
        if len(crossed) != 2:
            return None
        t, e, path, length = t0, crossed[first], [p0], 0.0
        while True:
            a, b = e
            sa, sb = side(a), side(b)
            q = tuple(mesh.v[a][k] + (mesh.v[b][k] - mesh.v[a][k]) * sa / (sa - sb) for k in range(3))
            length += norm(sub(q, path[-1])); path.append(q)
            if length > budget:
                break
            nxt = [x for x in mesh.edges[(min(a, b), max(a, b))] if x != t]
            if len(nxt) != 1:  # open border or non-manifold: this way is blocked
                break
            t = nxt[0]
            if t == t1:
                path.append(p1); length += norm(sub(p1, q))
                if best is None or length < best[0]:
                    best = (length, path)
                break
            v = mesh.t[t]
            e = next(((x, y) for x, y in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0]))
                      if {x, y} != {a, b} and (side(x) >= 0) != (side(y) >= 0)), None)
            if e is None:
                break
    return best[1] if best else None

def simplify(pts, tol):
    """Douglas-Peucker: drop points that sit within tol of the chord, so splines stay light on dense scans."""
    if len(pts) < 3:
        return pts
    i, dmax = max(((k, norm(sub(pts[k], closest_on_seg(pts[k], pts[0], pts[-1])))) for k in range(1, len(pts)-1)),
                  key=lambda x: x[1])
    if dmax <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[:i+1], tol)[:-1] + simplify(pts[i:], tol)

def resample(pts, n):
    """n+1 points evenly spaced by arc length along the polyline."""
    acc = [0.0]
    for i in range(len(pts)-1):
        acc.append(acc[-1] + norm(sub(pts[i+1], pts[i])))
    out, k = [], 0
    for j in range(n+1):
        s = acc[-1] * j / n
        while k < len(pts)-2 and acc[k+1] < s:
            k += 1
        seg = (acc[k+1] - acc[k]) or 1.0
        t = min(max((s - acc[k]) / seg, 0.0), 1.0)
        out.append(tuple(pts[k][c] + (pts[k+1][c] - pts[k][c]) * t for c in range(3)))
    return out

def fair_on_mesh(mesh, pts, iters=12):
    """Smooth the polyline (ends fixed) and press it back onto the mesh each pass: follows the part's shape,
    not the scan noise. ponytail: small-step Laplacian, may round a crisp edge the line crosses by ~2 samples."""
    L = sum(norm(sub(pts[i+1], pts[i])) for i in range(len(pts)-1))
    n = max(8, min(60, int(L / 0.02)))  # ~0.2 mm samples, 8..60 per line
    p = resample(pts, n)
    for _ in range(iters):
        p = [p[0]] + [mesh.closest(tuple(0.5*p[i][c] + 0.25*(p[i-1][c] + p[i+1][c]) for c in range(3)))[0]
                      for i in range(1, n)] + [p[-1]]
    return p

def snap_curve(mesh, p0, p1, n=8):
    """Smooth points from p0 to p1 lying on the mesh: the surface walk (else the chord pulled onto it), faired."""
    path = surface_path(mesh, p0, p1)
    if not path:
        path = [p0]
        for i in range(1, n):
            t = i/n
            q = (p0[0]+(p1[0]-p0[0])*t, p0[1]+(p1[1]-p0[1])*t, p0[2]+(p1[2]-p0[2])*t)
            for _ in range(2):
                q = mesh.closest(q)[0]
            path.append(q)
        path.append(p1)
    if len(path) == 2:
        return path
    return simplify(fair_on_mesh(mesh, path), 0.005)

def chains(edges):
    """Split the line graph into runs through degree-2 nodes: [[a, b, c, ...], ...]; closed run ends where it starts."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    used, out = set(), []
    key = lambda a, b: (min(a, b), max(a, b))
    def walk(a, b):
        run = [a, b]; used.add(key(a, b))
        while len(adj[b]) == 2 and b != run[0]:
            c = next((x for x in adj[b] if key(b, x) not in used), None)
            if c is None:
                break
            used.add(key(b, c)); run.append(c); b = c
        return run
    for a in adj:  # open runs start at ends/junctions
        if len(adj[a]) != 2:
            for b in adj[a]:
                if key(a, b) not in used:
                    out.append(walk(a, b))
    for a, b in edges:  # what's left are closed loops
        if key(a, b) not in used:
            out.append(walk(a, b))
    return out

def smooth_grow(mesh, seeds, max_angle, limit=None):
    """Flood fill across edges whose dihedral is below max_angle (radians)."""
    cos_lim = math.cos(max_angle)
    seen = set(seeds)
    q = deque(seeds)
    while q:
        t = q.popleft()
        for n in mesh.nb[t]:
            if n not in seen and dot(mesh.nrm[t], mesh.nrm[n]) >= cos_lim:
                seen.add(n); q.append(n)
                if limit and len(seen) >= limit:
                    return seen
    return seen

def model_grow(mesh, seeds, model, dist_tol, ang_tol):
    """Flood fill keeping triangles whose vertices sit on the model and whose normal agrees with it."""
    cos_lim = math.cos(ang_tol)
    def ok(t):
        if any(abs(model.dist(mesh.v[i])) > dist_tol for i in mesh.t[t]):
            return False
        return abs(dot(mesh.nrm[t], model.normal(mesh.cen[t]))) >= cos_lim
    seen = {s for s in seeds}
    q = deque(seen)
    while q:
        t = q.popleft()
        for n in mesh.nb[t]:
            if n not in seen and ok(n):
                seen.add(n); q.append(n)
    return seen

def robust_fit(kind, v, fp, fn, dist_tol):
    """Fit, then refit on inliers only (|dist| <= max(tol, 2.5 robust sigma)), so a few scan spikes can't tilt the model."""
    model = fit(kind, v, fp, fn)
    for _ in range(2):
        if model is None or len(v) < 8:
            return model
        d = sorted(abs(model.dist(p)) for p in v)
        cut = max(dist_tol, 2.5*1.4826*d[len(d)//2])
        keep = [p for p in v if abs(model.dist(p)) <= cut]
        if len(keep) == len(v) or len(keep) < 6:
            return model
        kf = [i for i, p in enumerate(fp) if abs(model.dist(p)) <= cut]
        m2 = fit(model.kind, keep, [fp[i] for i in kf], [fn[i] for i in kf])
        if m2 is None:
            return model
        model, v = m2, keep
    return model

def detect(mesh, seeds, kind='auto', dist_tol=0.005, smooth_angle=math.radians(25), iters=3, strict=False):
    """seeds: triangle indices. Returns (model, triangle set). dist_tol in mesh units (cm in Fusion).
    strict: return (None, region) when the best shape still misses the scan by more than the tolerance."""
    region = smooth_grow(mesh, seeds, smooth_angle)
    model = None
    for _ in range(iters):
        v, fp, fn = mesh.region_data(list(region))
        if len(fn) < 2 and kind != 'plane':
            v, fp, fn = mesh.region_data(list(smooth_grow(mesh, seeds, math.pi/2, limit=50)))
        model = robust_fit(kind, v, fp, fn, dist_tol)
        if model is None:
            return None, region
        tol = min(max(dist_tol, 3*model.rms), 3*dist_tol)  # noise may widen the band, but never past 3x what the user asked
        grown = model_grow(mesh, seeds, model, tol, math.radians(20))
        if grown == region:
            break
        region = grown | set(seeds)
    v, fp, fn = mesh.region_data(list(region))
    m2 = robust_fit(model.kind, v, fp, fn, dist_tol) or model  # final fit on the final region, same type
    if strict and (m2.rms > 3*dist_tol or len(region) < 2):
        return None, region
    return m2, region

def boundary_loops(mesh, tris):
    """Closed vertex-index loops along the region border (edges used by one region triangle)."""
    cnt = {}
    for t in tris:
        a, b, c = mesh.t[t]
        for e in ((a, b), (b, c), (c, a)):
            k = (min(e), max(e))
            cnt[k] = cnt.get(k, 0) + 1
    adj = {}
    for (a, b), n in cnt.items():
        if n == 1:
            adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    loops, used = [], set()
    for s in adj:
        if s in used:
            continue
        loop, prev, cur = [s], None, s
        used.add(s)
        while True:
            nxt = next((n for n in adj[cur] if n != prev and n not in used), None)
            if nxt is None:
                break
            loop.append(nxt); used.add(nxt); prev, cur = cur, nxt
        if len(loop) >= 3:
            loops.append(loop)
    return loops

def deviation(ref, pts):
    """Signed distance of each point to the reference mesh (+ = outside, along the reference normal)."""
    out = []
    for p in pts:
        q, t = ref.closest(p)
        d = norm(sub(p, q))
        out.append(d if dot(sub(p, q), ref.nrm[t]) >= 0 else -d)
    return out

def heat(d, tol, rng):
    """RGBA for a deviation: green inside tol, to red (+) / blue (-) at rng, saturated beyond."""
    if abs(d) <= tol:
        return (40, 200, 70, 255)
    t = min(1.0, (abs(d) - tol) / max(rng - tol, 1e-12))
    if d > 0:  # yellow -> red
        return (255, int(220 * (1 - t)), 0, 255)
    return (0, int(200 * (1 - t)), 255, 255)  # cyan -> blue

class SnapIndex:
    """Grid over snap targets (points + segments) so a mouse move only tests what is near the cursor."""
    def __init__(self, verts, segs, cell):
        self.cell = max(cell, 1e-6)
        self.v, self.s = {}, {}
        k = self._k
        for p in verts:
            self.v.setdefault(k(p), []).append(p)
        for a, b in segs:
            n = max(1, int(norm(sub(b, a)) / self.cell))  # long segments land in every cell they cross
            for c in {k(tuple(a[j] + (b[j]-a[j]) * t / n for j in range(3))) for t in range(n + 1)}:
                self.s.setdefault(c, []).append((a, b))

    def _k(self, p):
        return (int(math.floor(p[0]/self.cell)), int(math.floor(p[1]/self.cell)), int(math.floor(p[2]/self.cell)))

    def near(self, p, r):
        c, n = self._k(p), int(r / self.cell) + 1
        cells = [(c[0]+i, c[1]+j, c[2]+k) for i in range(-n, n+1) for j in range(-n, n+1) for k in range(-n, n+1)]
        return [v for x in cells for v in self.v.get(x, ())], list({s for x in cells for s in self.s.get(x, ())})
