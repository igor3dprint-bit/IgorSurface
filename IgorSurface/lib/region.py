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

def snap_curve(mesh, p0, p1, n=8):
    """n+1 points from p0 to p1 pulled onto the mesh (iterated so the curve hugs the surface)."""
    pts = [p0]
    for i in range(1, n):
        t = i/n
        q = (p0[0]+(p1[0]-p0[0])*t, p0[1]+(p1[1]-p0[1])*t, p0[2]+(p1[2]-p0[2])*t)
        for _ in range(2):
            q = mesh.closest(q)[0]
        pts.append(q)
    return pts + [p1]

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

def detect(mesh, seeds, kind='auto', dist_tol=0.005, smooth_angle=math.radians(25), iters=3):
    """seeds: triangle indices. Returns (model, triangle set). dist_tol in mesh units (cm in Fusion)."""
    region = smooth_grow(mesh, seeds, smooth_angle)
    model = None
    for _ in range(iters):
        v, fp, fn = mesh.region_data(list(region))
        if len(fn) < 2 and kind != 'plane':
            v, fp, fn = mesh.region_data(list(smooth_grow(mesh, seeds, math.pi/2, limit=50)))
        model = fit(kind, v, fp, fn)
        if model is None:
            return None, region
        tol = max(dist_tol, 3*model.rms)
        grown = model_grow(mesh, seeds, model, tol, math.radians(20))
        if grown == region:
            break
        region = grown | set(seeds)
    v, fp, fn = mesh.region_data(list(region))
    m2 = fit(model.kind, v, fp, fn)  # final fit on the final region, same type
    return (m2 or model), region

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
