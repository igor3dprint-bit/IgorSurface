"""Scan helpers, pure Python: align frame, symmetry plane, PLY reading and binary STL writing."""
import math, struct
from .fit import sub, add, mul, dot, cross, unit, norm, mean, cov, eig_sym3

# ---------- alignment ----------

def frame(floor_origin, floor_n, pts, x_hint=None):
    """Rigid transform (R rows, t) taking the scan so the floor is z=0 facing up, X along x_hint (or the
    scan's longest direction) and the footprint centered on the origin: new = R*p + t."""
    z = unit(floor_n)
    if dot(sub(mean(pts), floor_origin), z) < 0:  # the part sits on top of its floor
        z = mul(z, -1)
    if x_hint is None or norm(sub(x_hint, mul(z, dot(x_hint, z)))) < 1e-6:
        flat = [sub(p, mul(z, dot(p, z))) for p in pts[::max(1, len(pts)//5000)]]
        x_hint = eig_sym3(cov(flat, mean(flat)))[2][1]
    x = unit(sub(x_hint, mul(z, dot(x_hint, z))))
    y = cross(z, x)
    R = (x, y, z)
    loc = [tuple(dot(r, sub(p, floor_origin)) for r in R) for p in pts]
    cx = (min(q[0] for q in loc) + max(q[0] for q in loc)) / 2
    cy = (min(q[1] for q in loc) + max(q[1] for q in loc)) / 2
    t = tuple(-dot(r, floor_origin) for r in R)
    return R, (t[0] - cx, t[1] - cy, t[2])

def apply(R, t, p):
    return tuple(dot(r, p) + t[i] for i, r in enumerate(R))

# ---------- symmetry ----------

def reflect(p, o, n):
    return sub(p, mul(n, 2 * dot(sub(p, o), n)))

def symmetry(mesh, n_sample=1500, iters=15):
    """Best mirror plane (origin, normal, rms) of a mesh: PCA candidates, then ICP-style refinement."""
    pts = mesh.v[::max(1, len(mesh.v) // n_sample)]
    c = mean(pts)
    def score(o, n):
        return math.sqrt(sum(norm(sub(r, mesh.closest(r)[0]))**2 for r in (reflect(p, o, n) for p in pts)) / len(pts))
    cands = [e[1] for e in eig_sym3(cov(pts, c))]
    o, n = c, min(cands, key=lambda n: score(c, n))
    for _ in range(iters):
        pairs = [(p, mesh.closest(reflect(p, o, n))[0]) for p in pts]
        # q ~ mirror image of p: the plane bisects p and reflect(q)
        mids, dirs = [], []
        for p, q in pairs:
            q2 = reflect(q, o, n)
            d = sub(p, q2)
            if norm(d) > 1e-9:
                dirs.append(mul(unit(d), 1 if dot(d, n) >= 0 else -1))
            mids.append(mul(add(p, q2), 0.5))
        if not dirs:
            break
        n2 = unit(mean(dirs))
        o2 = mean(mids)
        if norm(sub(n2, n)) < 1e-9 and norm(sub(o2, o)) < 1e-9:
            break
        n, o = n2, o2
    return o, n, score(o, n)

# ---------- files ----------

_PLY_T = {'char': 'b', 'uchar': 'B', 'int8': 'b', 'uint8': 'B', 'short': 'h', 'ushort': 'H', 'int16': 'h',
          'uint16': 'H', 'int': 'i', 'uint': 'I', 'int32': 'i', 'uint32': 'I', 'float': 'f', 'float32': 'f',
          'double': 'd', 'float64': 'd'}

def read_ply(path):
    """(vertices, faces) from an ASCII or binary PLY. Faces with more than 3 corners are fanned."""
    with open(path, 'rb') as f:
        data = f.read()
    end = data.index(b'end_header') + len(b'end_header')
    end = data.index(b'\n', end) + 1
    header = data[:end].decode('ascii', 'replace').splitlines()
    fmt, elems = 'ascii', []
    for line in header:
        w = line.split()
        if not w:
            continue
        if w[0] == 'format':
            fmt = w[1]
        elif w[0] == 'element':
            elems.append([w[1], int(w[2]), []])
        elif w[0] == 'property':
            elems[-1][2].append(('list', w[2], w[3], w[4]) if w[1] == 'list' else (w[1], w[2]))
    verts, faces = [], []
    if fmt == 'ascii':
        tok = iter(data[end:].split())
        for name, count, props in elems:
            for _ in range(count):
                row = {}
                for pr in props:
                    if pr[0] == 'list':
                        row[pr[3]] = [float(next(tok)) for _ in range(int(next(tok)))]
                    else:
                        row[pr[1]] = float(next(tok))
                _keep(name, row, verts, faces)
    else:
        bo = '<' if 'little' in fmt else '>'
        pos = end
        for name, count, props in elems:
            for _ in range(count):
                row = {}
                for pr in props:
                    if pr[0] == 'list':
                        n, = struct.unpack_from(bo + _PLY_T[pr[1]], data, pos); pos += struct.calcsize(_PLY_T[pr[1]])
                        sz = struct.calcsize(_PLY_T[pr[2]])
                        row[pr[3]] = list(struct.unpack_from(bo + _PLY_T[pr[2]] * n, data, pos)); pos += sz * n
                    else:
                        v, = struct.unpack_from(bo + _PLY_T[pr[0]], data, pos); pos += struct.calcsize(_PLY_T[pr[0]])
                        row[pr[1]] = v
                _keep(name, row, verts, faces)
    return verts, faces

def _keep(name, row, verts, faces):
    if name == 'vertex':
        verts.append((float(row['x']), float(row['y']), float(row['z'])))
    elif name == 'face':
        idx = [int(i) for i in row.get('vertex_indices', row.get('vertex_index', []))]
        faces += [(idx[0], idx[k], idx[k+1]) for k in range(1, len(idx) - 1)]

def write_stl(path, verts, faces):
    with open(path, 'wb') as f:
        f.write(b'IgorSurface'.ljust(80, b' ') + struct.pack('<I', len(faces)))
        for a, b, c in faces:
            pa, pb, pc = verts[a], verts[b], verts[c]
            n = cross(sub(pb, pa), sub(pc, pa))
            l = norm(n) or 1.0
            f.write(struct.pack('<12fH', n[0]/l, n[1]/l, n[2]/l, *pa, *pb, *pc, 0))
