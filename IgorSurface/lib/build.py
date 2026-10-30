"""Turns a fitted Model into editable Fusion geometry (sketch-driven features, timeline friendly).
Fusion internal length unit is cm; every model coordinate here is cm."""
import math
import adsk.core, adsk.fusion
from .fit import sub, add, mul, dot, cross, unit, norm, perp_basis, mean

P3 = lambda p: adsk.core.Point3D.create(*p)
VI = adsk.core.ValueInput.createByReal
NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation

def _ref_plane(comp, o, u, v, name):
    """Parametric construction plane through o, o+u, o+v, driven by points of a reference sketch."""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = name + '_ref'
    pts = [sk.sketchPoints.add(sk.modelToSketchSpace(P3(p))) for p in (o, add(o, u), add(o, v))]
    sk.isVisible = False
    inp = comp.constructionPlanes.createInput()
    inp.setByThreePoints(*pts)
    pl = comp.constructionPlanes.add(inp)
    pl.name = name + '_plane'
    return pl, sk, pts

def _ang_range(model_axis, origin, pts):
    """(start_angle, sweep) of pts around the axis in the perp_basis frame; sweep=2pi if closed."""
    u, v = perp_basis(model_axis)
    angs = sorted(math.atan2(dot(sub(p, origin), v), dot(sub(p, origin), u)) for p in pts)
    gaps = [(angs[(i+1) % len(angs)] - angs[i]) % (2*math.pi) for i in range(len(angs))]
    i = max(range(len(gaps)), key=gaps.__getitem__)
    if gaps[i] < math.radians(20):
        return 0.0, 2*math.pi
    return angs[(i+1) % len(angs)], 2*math.pi - gaps[i]

def _hull(pts2):
    """Andrew monotone chain convex hull of 2D points."""
    p = sorted(set(pts2))
    if len(p) < 3:
        return p
    def half(seq):
        h = []
        for q in seq:
            while len(h) >= 2 and (h[-1][0]-h[-2][0])*(q[1]-h[-2][1]) - (h[-1][1]-h[-2][1])*(q[0]-h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h[:-1]
    return half(p) + half(reversed(p))

def _polyline(sk, pts2):
    """Closed polygon with shared endpoints (so it makes a profile)."""
    ln = sk.sketchCurves.sketchLines
    P = lambda q: adsk.core.Point3D.create(q[0], q[1], 0)
    lines = []
    for i in range(len(pts2)):
        s = lines[-1].endSketchPoint if lines else P(pts2[0])
        e = lines[0].startSketchPoint if i == len(pts2) - 1 else P(pts2[i+1])
        lines.append(ln.addByTwoPoints(s, e))

def build(comp, model, verts, name, surface=True, loops=None, tol=0.01):
    """Creates the feature(s) for model over the region vertices. loops: border polylines (planes).
    surface: True = surface body, False = construction only, 'sketch' = sketches only (lighter; tol cm cleans planar borders)."""
    if model.kind == 'plane':
        return _plane(comp, model, verts, name, surface, loops, tol)
    fn = {'cylinder': _cylinder, 'sphere': _sphere, 'cone': _cone}[model.kind]
    return fn(comp, model, verts, name, surface)

def _plane(comp, m, verts, name, surface, loops=None, tol=0.01):
    u, v = perp_basis(m.n)
    o = m.origin
    pl, _, _ = _ref_plane(comp, o, u, v, name)
    if not surface:
        return 'plano de construção'
    sk = comp.sketches.add(pl)
    sk.name = name
    to2 = lambda p: (lambda q: (q.x, q.y))(sk.modelToSketchSpace(P3(p)))
    sk.isComputeDeferred = True
    if surface == 'sketch':  # clean border: holes come out as real circles
        to_sk = lambda q: adsk.core.Point3D.create(q[0], q[1], 0)
        _curves(sk, [([to2(p) for p in lp], True) for lp in (loops or [])] or [(_hull([to2(p) for p in verts]), True)], tol, to_sk)
        sk.isComputeDeferred = False
        return 'esboço plano (%d contorno%s)' % (len(loops or [1]), '' if len(loops or [1]) == 1 else 's')
    if loops:  # real region border: outer contour + holes
        for lp in loops:
            _polyline(sk, [to2(p) for p in lp])
    else:
        _polyline(sk, _hull([to2(p) for p in verts]))
    sk.isComputeDeferred = False
    prof = max(sk.profiles, key=lambda pr: pr.areaProperties().area)
    pf = comp.features.patchFeatures
    patch = pf.add(pf.createInput(prof, NEW))
    patch.bodies.item(0).name = name
    return 'superfície plana'

def _axial(model_axis, origin, verts):
    hs = [dot(sub(p, origin), model_axis) for p in verts]
    return min(hs), max(hs)

def _cylinder(comp, m, verts, name, surface):
    h0, h1 = _axial(m.axis, m.origin, verts)
    base = add(m.origin, mul(m.axis, h0))
    u, v = perp_basis(m.axis)
    pl, _, ref = _ref_plane(comp, base, u, v, name)
    ai = comp.constructionAxes.createInput()
    top_sk = comp.sketches.add(comp.xYConstructionPlane); top_sk.isVisible = False; top_sk.name = name + '_axis'
    ai.setByTwoPoints(ref[0], top_sk.sketchPoints.add(top_sk.modelToSketchSpace(P3(add(base, m.axis)))))
    ax = comp.constructionAxes.add(ai); ax.name = name + '_axis'
    if not surface:
        return 'eixo + plano de construção'
    sk = comp.sketches.add(pl); sk.name = name
    c = sk.modelToSketchSpace(P3(base))
    start, sweep = _ang_range(m.axis, base, verts)
    if surface == 'sketch':  # both end rims in one sketch (off-plane circles are fine in Fusion)
        for h in (0, h1 - h0):
            cc = sk.modelToSketchSpace(P3(add(base, mul(m.axis, h))))
            if sweep >= 2*math.pi - 1e-9:
                sk.sketchCurves.sketchCircles.addByCenterRadius(cc, m.r)
            else:
                sp = sk.modelToSketchSpace(P3(add(add(base, mul(m.axis, h)), mul(add(mul(u, math.cos(start)), mul(v, math.sin(start))), m.r))))
                sk.sketchCurves.sketchArcs.addByCenterStartSweep(cc, sp, sweep)
        return 'esboço cilindro Ø%.3f mm' % (m.r*20)
    if sweep >= 2*math.pi - 1e-9:
        circ = sk.sketchCurves.sketchCircles.addByCenterRadius(c, m.r)
        sk.sketchDimensions.addDiameterDimension(circ, adsk.core.Point3D.create(c.x + m.r*1.2, c.y, 0))
        prof = sk.profiles.item(0)
    else:
        sp = sk.modelToSketchSpace(P3(add(base, mul(add(mul(u, math.cos(start)), mul(v, math.sin(start))), m.r))))
        arc = sk.sketchCurves.sketchArcs.addByCenterStartSweep(c, sp, sweep)
        sk.sketchDimensions.addRadialDimension(arc, adsk.core.Point3D.create(c.x + m.r*0.5, c.y, 0))
        prof = comp.features.createPath(arc, False)
    ex = comp.features.extrudeFeatures
    inp = ex.createInput(prof, NEW)
    inp.isSolid = False
    inp.setDistanceExtent(False, VI(max(h1 - h0, 1e-4)))
    f = ex.add(inp)
    f.bodies.item(0).name = name
    return 'cilindro Ø%.3f mm' % (m.r*20)

def _revolve(comp, sk, curve, axis_line, sweep, name):
    rv = comp.features.revolveFeatures
    prof = comp.features.createPath(curve, False)
    inp = rv.createInput(prof, axis_line, NEW)
    inp.isSolid = False
    inp.setAngleExtent(False, VI(sweep))
    f = rv.add(inp)
    f.bodies.item(0).name = name
    return f

def _sphere(comp, m, verts, name, surface):
    axis = unit(sub(mean(verts), m.c))
    u, _ = perp_basis(axis)
    start, sweep = _ang_range(axis, m.c, verts)
    uu, vv = perp_basis(axis)
    d0 = add(mul(uu, math.cos(start)), mul(vv, math.sin(start)))  # profile plane spans axis and d0
    pl, _, _ = _ref_plane(comp, m.c, axis, d0, name)
    if not surface:
        return 'plano de construção no centro'
    pol = [math.acos(max(-1, min(1, dot(unit(sub(p, m.c)), axis)))) for p in verts]
    a0, a1 = min(pol), max(pol)
    sk = comp.sketches.add(pl); sk.name = name
    c = sk.modelToSketchSpace(P3(m.c))
    pt = lambda a: sk.modelToSketchSpace(P3(add(m.c, mul(add(mul(axis, math.cos(a)), mul(d0, math.sin(a))), m.r))))
    lines = sk.sketchCurves.sketchLines
    axl = lines.addByTwoPoints(sk.modelToSketchSpace(P3(add(m.c, mul(axis, -m.r)))), sk.modelToSketchSpace(P3(add(m.c, mul(axis, m.r)))))
    axl.isConstruction = True
    arc = sk.sketchCurves.sketchArcs.addByThreePoints(pt(a0), pt((a0+a1)/2), pt(a1))
    sk.sketchDimensions.addRadialDimension(arc, adsk.core.Point3D.create(c.x + m.r*0.3, c.y + m.r*0.3, 0))
    if surface == 'sketch':
        return 'esboço esfera Ø%.3f mm' % (m.r*20)
    _revolve(comp, sk, arc, axl, sweep, name)
    return 'esfera Ø%.3f mm' % (m.r*20)

def _cone(comp, m, verts, name, surface):
    start, sweep = _ang_range(m.axis, m.apex, verts)
    uu, vv = perp_basis(m.axis)
    d0 = add(mul(uu, math.cos(start)), mul(vv, math.sin(start)))
    pl, _, _ = _ref_plane(comp, m.apex, m.axis, d0, name)
    if not surface:
        return 'plano de construção no eixo'
    h0, h1 = _axial(m.axis, m.apex, verts)
    gen = lambda h: sk.modelToSketchSpace(P3(add(m.apex, add(mul(m.axis, h), mul(d0, h*math.tan(m.ang))))))
    sk = comp.sketches.add(pl); sk.name = name
    lines = sk.sketchCurves.sketchLines
    axl = lines.addByTwoPoints(sk.modelToSketchSpace(P3(m.apex)), sk.modelToSketchSpace(P3(add(m.apex, mul(m.axis, h1)))))
    axl.isConstruction = True
    g = lines.addByTwoPoints(gen(h0), gen(h1))
    if surface == 'sketch':
        return 'esboço cone %.2f°' % math.degrees(m.ang)
    _revolve(comp, sk, g, axl, sweep, name)
    return 'cone %.2f° (meio-ângulo)' % math.degrees(m.ang)

def section_segs(mesh, o, n):
    """3D segments where the plane (point o, normal n) cuts the mesh. ponytail: scans every triangle,
    ~0.5 s on 300k in pure Python; add a slab index if the live preview feels slow."""
    segs = []
    for a, b, c in mesh.t:
        tri = (mesh.v[a], mesh.v[b], mesh.v[c])
        d = [dot(sub(p, o), n) for p in tri]
        cut = []
        for i in range(3):
            j = (i+1) % 3
            if (d[i] > 0) != (d[j] > 0):
                cut.append(add(tri[i], mul(sub(tri[j], tri[i]), d[i]/(d[i]-d[j]))))
        if len(cut) == 2 and dot(sub(cut[0], cut[1]), sub(cut[0], cut[1])) > 1e-12:
            segs.append((cut[0], cut[1]))
    return segs

def section(comp, plane_model, mesh, offset, name, tol=None):
    """Sketch on the fitted plane with the mesh cross-section at `offset` along the plane normal.
    tol (cm): fit clean lines/arcs/circles within it; None = raw segments. Returns the curve count."""
    from . import curve2d
    u, v = perp_basis(plane_model.n)
    o = add(plane_model.origin, mul(plane_model.n, offset))
    segs = [tuple((dot(sub(q, o), u), dot(sub(q, o), v)) for q in s) for s in section_segs(mesh, o, plane_model.n)]
    if not segs:
        return 0
    pl, _, _ = _ref_plane(comp, o, u, v, name)
    sk = comp.sketches.add(pl); sk.name = name
    to_sk = lambda q: sk.modelToSketchSpace(P3(add(o, add(mul(u, q[0]), mul(v, q[1])))))
    sk.isComputeDeferred = True
    n = _curves(sk, curve2d.chain(segs), tol, to_sk)
    sk.isComputeDeferred = False
    return n

def _curves(sk, chains, tol, to_sk):
    """Draws 2D chains [(pts, closed)] as clean lines/arcs/circles (tol cm; None = raw). Returns the curve count."""
    from . import curve2d
    curves = sk.sketchCurves
    n = 0
    for pts, closed in chains:
        raw = pts + [pts[0]] if closed else pts  # closed chains don't repeat the first point
        items = curve2d.fit(pts, closed, tol) if tol else [('line', raw[i], raw[i+1]) for i in range(len(raw)-1)]
        first = last = None
        for it in items:
            if it[0] == 'circle':
                curves.sketchCircles.addByCenterRadius(to_sk(it[1]), it[2]); n += 1
                continue
            start = last if last is not None else to_sk(it[1])
            if it[0] == 'line':
                c = curves.sketchLines.addByTwoPoints(start, to_sk(it[2]))
            else:
                c = curves.sketchArcs.addByThreePoints(start, to_sk(it[2]), to_sk(it[3]))
            first = first or c
            last = c.endSketchPoint
            n += 1
        if closed and first is not None and last is not None:
            last.merge(first.startSketchPoint)  # close the loop so it makes a profile
    return n
