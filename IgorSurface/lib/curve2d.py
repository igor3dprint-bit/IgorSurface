"""2D section cleanup: raw mesh-section segments -> chained polylines -> few lines, arcs and circles.
Pure Python. Points are (x, y) tuples."""
import math

def chain(segs, eps=1e-6):
    """Join segments sharing endpoints into polylines. Returns [(points, closed)]."""
    key = lambda p: (round(p[0]/eps), round(p[1]/eps))
    adj = {}
    for a, b in segs:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        adj.setdefault(ka, []).append((kb, b)); adj.setdefault(kb, []).append((ka, a))
    pos = {}
    for a, b in segs:
        pos[key(a)] = a; pos[key(b)] = b
    used, out = set(), []
    def walk(start):
        line, cur, prev = [start], start, None
        while True:
            nxt = next((k for k, _ in adj[cur] if k != prev and frozenset((cur, k)) not in used), None)
            if nxt is None:
                return line
            used.add(frozenset((cur, nxt)))
            if nxt == start:
                return line + [start]
            line.append(nxt); prev, cur = cur, nxt
    # open chains start at dead ends; what is left is closed loops
    for k in [k for k, v in adj.items() if len(v) == 1] + list(adj):
        if any(frozenset((k, n)) not in used for n, _ in adj[k]):
            ks = walk(k)
            pts = [pos[x] for x in ks]
            if len(pts) >= 2:
                out.append((pts[:-1], True) if len(ks) > 2 and ks[0] == ks[-1] else (pts, False))
    return out

def _dist_line(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    l = math.hypot(dx, dy)
    if l < 1e-12:
        return math.hypot(p[0]-a[0], p[1]-a[1])
    return abs((p[0]-a[0])*dy - (p[1]-a[1])*dx) / l

def circle(pts):
    """Kasa least-squares circle: (cx, cy, r) or None."""
    n = len(pts)
    if n < 3:
        return None
    mx = sum(p[0] for p in pts)/n; my = sum(p[1] for p in pts)/n
    suu = suv = svv = suuu = svvv = suvv = svuu = 0.0
    for x, y in pts:
        u, v = x-mx, y-my
        suu += u*u; suv += u*v; svv += v*v
        suuu += u*u*u; svvv += v*v*v; suvv += u*v*v; svuu += v*u*u
    det = suu*svv - suv*suv
    if abs(det) < 1e-18:
        return None
    b1, b2 = 0.5*(suuu + suvv), 0.5*(svvv + svuu)
    uc = (b1*svv - b2*suv)/det; vc = (suu*b2 - suv*b1)/det
    r = math.sqrt(uc*uc + vc*vc + (suu + svv)/n)
    return (uc + mx, vc + my, r)

def _arc_ok(pts, tol, max_r):
    c = circle(pts)
    if not c or c[2] > max_r:
        return None
    cx, cy, r = c
    if max(abs(math.hypot(x-cx, y-cy) - r) for x, y in pts) > tol:
        return None
    # the points must sweep monotonically around the center (a real arc, not a zig-zag)
    ang = [math.atan2(y-cy, x-cx) for x, y in pts]
    d = [((ang[i+1]-ang[i] + math.pi) % (2*math.pi)) - math.pi for i in range(len(ang)-1)]
    if not (all(x > 0 for x in d) or all(x < 0 for x in d)):
        return None
    return c, sum(d)

def fit(pts, closed, tol):
    """Polyline -> [('line', a, b) | ('arc', a, mid, b) | ('circle', (cx, cy), r)]."""
    if closed:
        a = _arc_ok(pts + [pts[0]], tol, 1e9)
        if a and abs(abs(a[1]) - 2*math.pi) < 0.2:
            return [('circle', a[0][:2], a[0][2])]
        # start the loop on its sharpest corner so no piece wraps around the seam
        i = max(range(len(pts)), key=lambda k: _turn(pts[k-1], pts[k], pts[(k+1) % len(pts)]))
        loop = pts[i:] + pts[:i+1]
        return _merge_lines(_greedy(loop, tol), tol, closed=True)
    return _merge_lines(_greedy(pts, tol), tol)

def _turn(a, b, c):
    u = (b[0]-a[0], b[1]-a[1]); v = (c[0]-b[0], c[1]-b[1])
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu < 1e-12 or nv < 1e-12:
        return 0.0
    return math.acos(max(-1.0, min(1.0, (u[0]*v[0] + u[1]*v[1]) / (nu*nv))))

def _greedy(pts, tol):
    """From the start, take the longest run that is a line or an arc within tol; repeat."""
    size = max(math.hypot(p[0]-pts[0][0], p[1]-pts[0][1]) for p in pts) or 1.0
    out, i, n = [], 0, len(pts)
    while i < n - 1:
        j_line = i + 1
        while j_line + 1 < n and max(_dist_line(p, pts[i], pts[j_line+1]) for p in pts[i:j_line+2]) <= tol:
            j_line += 1
        j_arc = None
        k = i + 3
        while k < n and _arc_ok(pts[i:k+1], tol, size*50):
            j_arc = k; k += 1
        if j_arc is not None and j_arc > j_line + 1:  # an arc must beat the line clearly to be worth it
            out.append(('arc', pts[i], pts[(i + j_arc)//2], pts[j_arc])); i = j_arc
        else:
            out.append(('line', pts[i], pts[j_line])); i = j_line
    return out

def _merge_lines(items, tol, closed=False):
    out = []
    for it in items:
        if out and it[0] == 'line' and out[-1][0] == 'line' and _dist_line(out[-1][2], out[-1][1], it[2]) <= tol:
            out[-1] = ('line', out[-1][1], it[2])
        else:
            out.append(it)
    if closed and len(out) > 1 and out[0][0] == out[-1][0] == 'line' and _dist_line(out[0][1], out[-1][1], out[0][2]) <= tol:
        out[0] = ('line', out[-1][1], out[0][2]); out.pop()
    return out
