"""Plano de Corte: pick a plane (flat area of the mesh, a construction plane or a planar face), drag the arrow
like an offset plane and watch the cut of the whole mesh live; OK makes the sketch with that cut."""
import math, re
import adsk.core, adsk.fusion
from ...lib import ui, region, build
from ...lib.fit import perp_basis, cross, dot, unit
from ..fitSurface.entry import mesh_of, to_component, reset_cache_check

CMD_ID = 'IgorSurface_planeSketch'
LOFT_ID = 'IgorSurface_autoLoft'
GROUP = 'Plano de corte'
BLUE = (47, 143, 216)
_state = {}

def start():
    ui.add_command(CMD_ID, 'Plano de Corte',
                   'Escolha um plano (área plana da malha, plano de construção ou face plana) e arraste a seta: '
                   'o corte da malha inteira aparece ao vivo. OK cria o esboço do corte.',
                   created)
    ui.add_command(LOFT_ID, 'Auto Transição',
                   'Selecione um grupo de cortes (ou um esboço dele): faz a transição (loft) pelos esboços '
                   'na ordem 1, 2, 3...', loft_created)

def stop():
    ui.remove_command(CMD_ID)
    ui.remove_command(LOFT_ID)

def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput('pick', 'Plano', 'Clique numa área plana da malha, num plano de construção ou numa face plana')
    for f in ('MeshBodies', 'ConstructionPlanes', 'PlanarFaces'):
        sel.addSelectionFilter(f)
    sel.setSelectionLimits(1, 1)
    inputs.addDistanceValueCommandInput('offset', 'Deslocar', adsk.core.ValueInput.createByString('0 mm'))
    inputs.addAngleValueCommandInput('tilt', 'Ângulo', adsk.core.ValueInput.createByString('0 deg'))
    inputs.addAngleValueCommandInput('turn', 'Giro', adsk.core.ValueInput.createByString('0 deg'))
    inputs.addIntegerSpinnerCommandInput('count', 'Cortes', 1, 100, 1, 1)
    inputs.addValueInput('step', 'Passo', 'mm', adsk.core.ValueInput.createByString('5 mm'))
    inputs.addBoolValueInput('clean', 'Limpo', True, '', True).tooltip = 'Converte o corte em retas, arcos e círculos.'
    inputs.addValueInput('ctol', 'Tol.', 'mm', adsk.core.ValueInput.createByString('0.05 mm'))
    inputs.addTextBoxCommandInput('info', '', 'Escolha o plano.', 2, True).isFullWidth = True
    _state.clear()
    reset_cache_check()
    ui.on(('select', cmd.select), lambda a: pick(a, inputs))
    ui.on(('select', cmd.unselect), lambda a: _state.pop('plane', None))
    ui.on(('command', cmd.executePreview), lambda a: show(inputs))
    ui.on(('command', cmd.execute), lambda a: run(a, inputs))
    ui.on(('command', cmd.destroy), lambda a: clear())

def first_mesh():
    d = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    for c in [d.rootComponent] + [o.component for o in d.rootComponent.allOccurrences]:
        for b in c.meshBodies:
            if b.isVisible:
                return b
    return None

def pick(args, inputs):
    """Plane in the mesh's component space: (body, origin, normal)."""
    e, info = args.selection.entity, inputs.itemById('info')
    if adsk.fusion.MeshBody.cast(e):
        body = adsk.fusion.MeshBody.cast(e)
        mesh = mesh_of(body)
        model, tris = region.detect(mesh, [mesh.nearest_tri(to_component(body, args.selection.point))], 'plane')
        if model is None or model.max > 0.05:  # > 0.5 mm off a plane is not a flat face
            info.text = 'Essa área não é plana. Clique numa face plana ou num plano.'
            _state.pop('plane', None)
            return
        n = model.n
        if sum(region.dot(mesh.nrm[t], n) for t in tris) > 0:  # point into the material
            n = tuple(-x for x in n)
        _state['plane'] = (body, model.origin, n)
    else:
        body = _state['plane'][0] if 'plane' in _state else first_mesh()
        if body is None:
            info.text = 'Nenhuma malha visível.'
            return
        g = e.geometry  # world plane
        o, tip = g.origin.copy(), g.origin.copy()
        v = g.normal.copy(); tip.translateBy(v)
        a, b = to_component(body, o), to_component(body, tip)
        _state['plane'] = (body, a, region.unit(region.sub(b, a)))
    info.text = 'Arraste a seta ou digite o deslocamento.'

def world(body, p):
    q = adsk.core.Point3D.create(*p)
    if body.assemblyContext:
        q.transformBy(body.assemblyContext.transform2)
    return q

def rot(x, k, t):
    """Rodrigues: x rotated by t around unit axis k."""
    c, s_, kx = math.cos(t), math.sin(t), cross(k, x)
    d = dot(k, x) * (1 - c)
    return tuple(x[i]*c + kx[i]*s_ + k[i]*d for i in range(3))

def normal(inputs):
    """Picked normal tilted around the plane's u axis (Ângulo), then around its v axis (Giro)."""
    body, o, n = _state['plane']
    u, v = perp_basis(n)
    return unit(rot(rot(n, u, inputs.itemById('tilt').value), v, inputs.itemById('turn').value))

def cuts(inputs):
    body, o, _ = _state['plane']
    n = normal(inputs)
    off, step = inputs.itemById('offset').value, inputs.itemById('step').value
    return [tuple(o[i] + n[i] * (off + k*step) for i in range(3)) for k in range(inputs.itemById('count').value)]

def clear():
    cg = _state.pop('cg', None)
    if cg and cg.isValid:
        cg.deleteMe()

def show(inputs):
    if 'plane' not in _state:
        return
    body, o, n0 = _state['plane']
    n = normal(inputs)
    u, v = perp_basis(n0)
    w = lambda d: world(body, o).vectorTo(world(body, tuple(o[i] + d[i] for i in range(3))))
    w0 = world(body, o)
    inputs.itemById('offset').setManipulator(w0, w(n))
    inputs.itemById('tilt').setManipulator(w0, w(n0), w(v))
    inputs.itemById('turn').setManipulator(w0, w(n0), w(u))
    mesh = mesh_of(body)
    segs = [x for c in cuts(inputs) for s in build.section_segs(mesh, c, n) for p in s for x in p]
    clear()
    g = body.parentComponent.customGraphicsGroups.add()
    g.id = ui.CG_ID
    if segs:
        ln = g.addLines(adsk.fusion.CustomGraphicsCoordinates.create(segs), list(range(len(segs) // 3)), False)
        ln.weight = 3; ln.depthPriority = 2
        ln.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*BLUE, 255))
    _state['cg'] = g
    inputs.itemById('info').text = ('%d trechos de corte.' % (len(segs) // 6)) if segs else 'O plano não corta a malha aqui.'

def run(args, inputs):
    if 'plane' not in _state:
        return
    body = _state['plane'][0]
    n = normal(inputs)
    clear()
    # tidy browser: <body comp>/Plano de corte/Corte manual N/Corte 1..k (identity transforms = same space as the mesh)
    parent = body.parentComponent
    top = next((o.component for o in parent.occurrences if o.component.name == GROUP), None)
    if top is None:
        top = parent.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        top.name = GROUP
    comp = top.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
    comp.name = 'Corte manual %d' % top.occurrences.count
    first = 1
    tol = inputs.itemById('ctol').value if inputs.itemById('clean').value else None
    mesh = mesh_of(body)
    model = type('Plane', (), {})()
    model.n = n
    segs = 0
    for k, c in enumerate(cuts(inputs)):
        model.origin = c
        segs += build.section(comp, model, mesh, 0.0, 'Corte %d' % (first + k), tol)
    if segs == 0:
        ui.ui.messageBox('O plano não cortou a malha. Arraste a seta até a peça.', 'IgorSurface')


# ---------- Auto Transição ----------

def loft_created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput('grp', 'Grupo', 'Clique num grupo de cortes (no navegador) ou num esboço dele')
    sel.addSelectionFilter('Occurrences')
    sel.addSelectionFilter('Sketches')
    sel.setSelectionLimits(1, 1)
    inputs.addBoolValueInput('solid', 'Sólido', True, '', True).tooltip = 'Desligado: só a superfície da transição.'
    ui.on(('command', cmd.execute), lambda a: loft_run(a, inputs))

def num(name):
    m = re.findall(r'\d+', name)
    return int(m[-1]) if m else 0

def outer_profile(sk):
    """The profile that bounds the whole cut (biggest box); holes stay inside it."""
    best = None
    for p in sk.profiles:
        b = p.boundingBox
        d = b.minPoint.distanceTo(b.maxPoint)
        if best is None or d > best[0]:
            best = (d, p)
    return best[1] if best else None

def loft_run(args, inputs):
    e = inputs.itemById('grp').selection(0).entity
    sk = adsk.fusion.Sketch.cast(e)
    comp = sk.parentComponent if sk else adsk.fusion.Occurrence.cast(e).component
    sketches = sorted((s for s in comp.sketches if s.profiles.count), key=lambda s: num(s.name))
    profs = [outer_profile(s) for s in sketches]
    if len(profs) < 2:
        ui.ui.messageBox('Preciso de pelo menos 2 esboços fechados nesse grupo.', 'IgorSurface')
        args.executeFailed = True
        return
    lofts = comp.features.loftFeatures
    li = lofts.createInput(adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    for p in profs:
        li.loftSections.add(p)
    li.isSolid = inputs.itemById('solid').value
    try:
        lofts.add(li)
    except RuntimeError as ex:
        ui.ui.messageBox('A transição falhou: %s\nConfira se cada corte é um contorno fechado.' % ex, 'IgorSurface')
        args.executeFailed = True
