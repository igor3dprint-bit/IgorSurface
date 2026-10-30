"""Malha Manual: the user builds a quad/tri net on the mesh by hand, in 3 modes (radio, Tab cycles):
Pontos = click adds a node, drag a node to move it; Linhas = click node after node to chain lines, click off a node
to end the chain; Pausa = clicks do nothing. Every closed loop of 3-4 lines is a face.
While working everything is light custom graphics; the real sketch is built only on OK (no surfaces)."""
import os, time
import adsk.core, adsk.fusion
from ...lib import ui, region
from ..fitSurface.entry import mesh_of, to_component, reset_cache_check

CMD_ID = 'IgorSurface_quadPatch'
ORANGE, BLUE = (243, 156, 18), (47, 143, 216)
MODES = ('Pontos', 'Linhas', 'Pausa')
IMG = {k: os.path.join(ui.RES, k + '.png') for k in ('point', 'point_active', 'point_ghost', 'point_ghost_snap')}
_state = {}

def start():
    ui.add_command(CMD_ID, 'Malha Manual',
                   'Monte a malha à mão seguindo a peça. Pontos: clique cria, clique num ponto apaga, arraste move. Linhas: clique ponto '
                   'após ponto. Pausa: só olhar. Tab troca o modo. Linhas fechando 3 ou 4 pontos viram face.',
                   created, promote=True)

def stop():
    ui.remove_command(CMD_ID)

# ---------- pure graph logic ----------

def faces_from_edges(edges):
    """Closed loops of 3 or 4 lines -> faces (node loops in order). A quad split by a diagonal stays two triangles."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
    es = {frozenset(e) for e in edges}
    faces, seen = [], set()
    for a, b in edges:
        for c in adj[a] & adj[b]:
            k = frozenset((a, b, c))
            if k not in seen:
                seen.add(k); faces.append([a, b, c])
    for a in adj:
        for b in adj[a]:
            for c in adj[b] - {a}:
                for d in (adj[c] & adj[a]) - {b}:
                    if frozenset((a, c)) in es or frozenset((b, d)) in es:
                        continue  # has a diagonal: already two triangles
                    k = frozenset((a, b, c, d))
                    if len(k) == 4 and k not in seen:
                        seen.add(k); faces.append([a, b, c, d])
    return faces

# ---------- command ----------

def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    rg = inputs.addRadioButtonGroupCommandInput('mode', 'Modo')
    for i, m in enumerate(MODES):
        rg.listItems.add(m, i == 0)
    rg.tooltip = 'Pontos: clique cria, clique num ponto apaga, arraste move. Linhas: clique ponto após ponto; clique fora de um ponto encerra. ' \
                 'Pausa: clique não faz nada. Tab troca o modo.'
    def opt(id_, label, tip, value=True):  # dialog is narrow: short label, explanation in the tooltip
        i = inputs.addBoolValueInput(id_, label, True, '', value)
        i.tooltip = tip
    opt('snapmesh', 'Snap malha', 'Grudar nos pontos e linhas que você criou.')
    opt('snappart', 'Snap peça', 'Grudar nos cantos e quinas do STL. Desligue em scan com muito ruído.')
    s = inputs.addIntegerSliderCommandInput('snappx', 'Raio (px)', 4, 40)
    s.valueOne = 12
    s.tooltip = 'Distância em pixels de tela para grudar e para pegar um ponto.'
    u = inputs.addBoolValueInput('undo', 'Desfazer', False, '', False)
    u.tooltip = 'Desfaz o último ponto, linha ou movimento.'
    inputs.addTextBoxCommandInput('info', 'Status', 'Modo Pontos: clique na peça.', 2, True)
    _state.clear()
    # pts: node coordinates; nodes: live node ids; edges: [(a, b)]; history: undo stack
    _state.update(pts=[], nodes=[], edges=[], history=[], body=None, cg=None, gg=None, gimg=None, ghost=None,
                  grab=None, hover=None, chain=None, cmd=cmd, inputs=inputs, mesh_comps=None,
                  last_move=(0.0, None), screen=(None, {}), index=None)
    ui.purge_graphics()
    reset_cache_check()
    # faces from earlier runs snap too; their geometry is read once
    pt = lambda v: (v.geometry.x, v.geometry.y, v.geometry.z)
    old = [b for b in all_bodies() if b.name.startswith('Face ')]  # surfaces from older versions
    segs = [(pt(e.startVertex), pt(e.endVertex)) for b in old for e in b.edges]
    for sk in all_sketches():  # current runs: 'Perímetros N' sketches
        to_m = lambda q: (lambda r: (r.x, r.y, r.z))(sk.sketchToModelSpace(q))
        segs += [(to_m(l.startSketchPoint.geometry), to_m(l.endSketchPoint.geometry)) for l in sk.sketchCurves.sketchLines]
    _state['old_segs'] = segs
    _state['old_verts'] = list({p for sg in segs for p in sg})
    left = adsk.core.MouseButtons.LeftMouseButton
    ui.on(('mouse', cmd.mouseClick), lambda a: click(a) if a.button == left else None)
    ui.on(('mouse', cmd.mouseMove), hover)
    ui.on(('mouse', cmd.mouseDragBegin), drag_begin)
    ui.on(('mouse', cmd.mouseDrag), drag)
    ui.on(('mouse', cmd.mouseDragEnd), drag_end)
    ui.on(('keyboard', cmd.keyDown), key)
    ui.on(('inputChanged', cmd.inputChanged), changed)
    # always valid so the preview runs: changing an input (mode, snap...) rolls back the preview and wipes the custom
    # graphics, so the cheap preview just redraws them. Nothing heavy until OK (empty net = OK does nothing).
    ui.on(('validate', cmd.validateInputs), lambda a: setattr(a, 'areInputsValid', True))
    ui.on(('command', cmd.executePreview), preview)
    ui.on(('command', cmd.execute), lambda a: build(inputs))
    ui.on(('command', cmd.destroy), lambda a: (clear_graphics(), clear_ghost(), restore_opacity()))

def preview(args):
    b = _state['body']
    if b and b.isValid:
        b.opacity = 0.45  # rolled back with the preview too
    redraw()  # old groups, if the rollback left them, are deleted inside draw()

def mode():
    return _state['inputs'].itemById('mode').selectedItem.name

def key(args):
    if args.keyCode == adsk.core.KeyCodes.TabKeyCode:
        items = _state['inputs'].itemById('mode').listItems
        items.item((MODES.index(mode()) + 1) % len(MODES)).isSelected = True
        mode_changed()

def mode_changed():
    _state['chain'] = None
    status()
    redraw()

def restore_opacity():
    b, op = _state.pop('opacity', (None, None))
    if b and b.isValid:
        b.opacity = op

def use_body(body):
    if _state['body'] != body:  # see-through mesh while working, restored on close
        if _state['body']:
            _state.update(pts=[], nodes=[], edges=[], history=[], chain=None)
        restore_opacity()
        _state['opacity'] = (body, body.opacity)
        body.opacity = 0.45
        _state['index'] = None
    _state['body'] = body

def add_node(p):
    _state['pts'].append(p)
    i = len(_state['pts']) - 1
    _state['nodes'].append(i)
    _state['history'].append(('node', i))
    _state['screen'] = (None, {})
    return i

def add_edge(a, b):
    if a == b or any({a, b} == set(e) for e in _state['edges']):
        return False
    _state['edges'].append((a, b))
    _state['history'].append(('edge', (a, b)))
    return True

def click(args):
    m = mode()
    if m == 'Pausa':
        return
    update_ghost(args)
    g = _state['ghost']
    if m == 'Linhas':
        n = g[3] if g else None
        if n is None:
            _state['chain'] = None  # clicked off a node: the chain ends
            status('Sequência encerrada. Clique num ponto para começar outra.')
        else:
            if _state['chain'] is not None:
                add_edge(_state['chain'], n)
            _state['chain'] = n
            status()
        redraw()
        return
    if not g:
        return
    body, p, snapped, node = g
    use_body(body)
    if node is not None:  # clicking an existing node deletes it, with its lines
        gone = [e for e in _state['edges'] if node in e]
        _state['edges'] = [e for e in _state['edges'] if node not in e]
        _state['nodes'].remove(node)
        _state['history'].append(('del', node, gone))
        if _state['chain'] == node:
            _state['chain'] = None
        _state['screen'] = (None, {})
        status('Ponto apagado (Desfazer traz de volta).')
        redraw()
        return
    add_node(p)
    status(snapped=snapped)
    redraw()

def ray_hit(args):
    """(mesh body, point in its component space) under the mouse, nearest to the eye, or None."""
    vp = args.viewport
    near = vp.viewToModelSpace(args.viewportPosition)
    cam = vp.camera
    persp = cam.cameraType == adsk.core.CameraTypes.PerspectiveCameraType
    d = cam.eye.vectorTo(near) if persp else cam.eye.vectorTo(cam.target)  # ray through the mouse
    o = near.copy(); back = d.copy(); back.normalize(); back.scaleBy(-1000); o.translateBy(back)
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    only = _state['body']
    best = None
    if _state.get('mesh_comps') is None:
        _state['mesh_comps'] = [c for c in (design.allComponents if design else []) if c.meshBodies.count]
    for comp in _state['mesh_comps']:
        found, hits = comp.findMeshUsingRay(o, d)
        for b, h in zip(found, hits):
            if (only is None or b == only) and b.isVisible:
                dist = o.distanceTo(h)
                if best is None or dist < best[0]:
                    best = (dist, b, h)
    if not best:
        return None
    b = best[1]
    return b, mesh_of(b).closest(to_component(b, best[2]))[0]

def update_ghost(args, skip=None):
    """Where a click would land right now: an existing node under the cursor, else ray hit + snap."""
    node = corner_at(args, skip)
    if node is not None:
        _state['ghost'] = (_state['body'], _state['pts'][node], True, node)
    elif mode() == 'Linhas':
        _state['ghost'] = None  # lines only connect existing nodes
    else:
        h = ray_hit(args)
        if h:
            body, p = h
            q = snap(body, p, tol_at(args, p), skip) if body == _state['body'] or _state['body'] is None else None
            _state['ghost'] = (body, q or p, q is not None, None)
        else:
            _state['ghost'] = None
    draw_ghost()

def clear_ghost():
    gg = _state.get('gg')
    if gg and gg.isValid:
        gg.deleteMe()
    _state.update(gg=None, gimg=None)

def draw_ghost():
    """One small graphics group: the ghost dot, plus the rubber line from the chain start in Linhas mode."""
    g = _state['ghost']
    chain = _state['chain'] if mode() == 'Linhas' else None
    if not g and chain is None:
        clear_ghost(); adsk.core.Application.get().activeViewport.refresh()
        return
    img = IMG['point_ghost_snap' if g and g[2] else 'point_ghost']
    old = _state.get('gg')  # ponytail: new group drawn before the old one goes, so nothing blinks
    comp = (g[0] if g else _state['body']).parentComponent
    grp = comp.customGraphicsGroups.add()
    grp.id = ui.CG_ID
    if g:
        ps = grp.addPointSet(adsk.fusion.CustomGraphicsCoordinates.create(list(g[1])), [0],
                             adsk.fusion.CustomGraphicsPointTypes.UserDefinedCustomGraphicsPointType, img)
        ps.depthPriority = 3
        if chain is not None and g[3] is not None and g[3] != chain:
            ln = grp.addLines(adsk.fusion.CustomGraphicsCoordinates.create(list(_state['pts'][chain]) + list(g[1])), [0, 1], False)
            ln.weight = 3; ln.color = color(ORANGE); ln.depthPriority = 2
    _state.update(gg=grp, gimg=img)
    if old and old.isValid:
        old.deleteMe()
    adsk.core.Application.get().activeViewport.refresh()  # graphics changed in a mouse event don't redraw by themselves

def all_sketches():
    d = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    return [s for c in d.allComponents for s in c.sketches if s.name.startswith('Perímetros ')] if d else []

def all_bodies():
    d = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    return [b for c in d.allComponents for b in c.bRepBodies] if d else []

def snap_index(body):
    """Grid of the static snap targets (STL crisp edges + earlier faces), built once per mesh."""
    if _state['index'] is None:
        m = mesh_of(body)
        sharp_segs, sharp_verts = m.sharp()
        _state['index'] = (region.SnapIndex(sharp_verts, sharp_segs, m.cell * 4),
                           region.SnapIndex(_state['old_verts'], _state['old_segs'], m.cell * 4))
    return _state['index']

def snap(body, p, tol, skip=None):
    """Snapped position for p within tol (model units), or None. Corners win over edges.
    Snap malha: nodes/lines made here + faces from earlier runs. Snap peça: crisp corners/edges of the STL."""
    inputs = _state['inputs']
    if not body:
        return None
    part, old = snap_index(body)
    verts, segs = [], []
    if inputs.itemById('snapmesh').value:
        P = _state['pts']
        v, s = old.near(p, tol)
        verts += v + [P[i] for i in _state['nodes'] if i != skip]
        segs += s + [(P[a], P[b]) for a, b in _state['edges'] if skip not in (a, b)]
    if inputs.itemById('snappart').value:
        v, s = part.near(p, tol)
        verts += v; segs += s
    return region.snap_point(p, tol, verts, segs)

def tol_at(args, p):
    """Snap radius in model units: the slider's pixels measured at p's depth (same feel at any zoom)."""
    vp = args.viewport
    a = vp.modelToViewSpace(adsk.core.Point3D.create(*p))
    up = vp.camera.upVector.copy(); up.normalize(); up.scaleBy(0.1)  # 1 mm along screen-up
    q = adsk.core.Point3D.create(*p); q.translateBy(up)
    b = vp.modelToViewSpace(q)
    px_per_unit = max(((a.x-b.x)**2 + (a.y-b.y)**2) ** 0.5 / 0.1, 1e-9)
    return _state['inputs'].itemById('snappx').valueOne / px_per_unit

def status(msg=None, snapped=False):
    if msg is None:
        msg = '%s · %d pontos · %d linhas · %d faces' % (mode(), len(_state['nodes']), len(_state['edges']),
                                                        len(faces_from_edges(_state['edges'])))
        if snapped:
            msg += ' (snap)'
    _state['inputs'].itemById('info').text = msg

def changed(args):
    if args.input.id == 'mode':
        mode_changed()
        return
    if args.input.id != 'undo':
        return
    args.input.value = False
    if not _state['history']:
        return
    kind, data, *rest = _state['history'].pop()
    if kind == 'node':
        _state['nodes'].remove(data)
        if _state['chain'] == data:
            _state['chain'] = None
    elif kind == 'edge':
        _state['edges'].remove(data)
    elif kind == 'move':
        _state['pts'][data] = rest[0]
    elif kind == 'del':
        _state['nodes'].append(data)
        _state['edges'] += rest[0]
    _state['screen'] = (None, {})
    status()
    redraw()

def clear_graphics():
    cg = _state.get('cg')
    if cg and cg.isValid:
        cg.deleteMe()
    _state['cg'] = None

def color(rgb, a=255):
    return adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*rgb, a))

def draw(comp, refresh=True):
    """The whole net as light graphics: translucent faces, blue lines, node dots (blue = active)."""
    old = _state.get('cg')  # deleted only after the new group exists: delete-then-add made nodes blink
    g = comp.customGraphicsGroups.add()
    g.id = ui.CG_ID
    P = _state['pts']
    coords = adsk.fusion.CustomGraphicsCoordinates.create([x for p in P for x in p])
    tris = [i for f in faces_from_edges(_state['edges']) for i in ([f[0], f[1], f[2]] + ([f[0], f[2], f[3]] if len(f) == 4 else []))]
    if tris:
        fm = g.addMesh(coords, tris, [], [])
        fm.color = color(BLUE, 90); fm.depthPriority = 1
    if _state['edges']:
        ln = g.addLines(coords, [i for e in _state['edges'] for i in e], False)
        ln.weight = 2; ln.color = color(BLUE); ln.depthPriority = 2
    active = {i for i in (_state['grab'], _state['hover'], _state['chain']) if i is not None}
    for img, idx in ((IMG['point'], [i for i in _state['nodes'] if i not in active]),
                     (IMG['point_active'], [i for i in _state['nodes'] if i in active])):
        if idx:
            ps = g.addPointSet(coords, idx, adsk.fusion.CustomGraphicsPointTypes.UserDefinedCustomGraphicsPointType, img)
            ps.depthPriority = 3
    _state['cg'] = g
    if old and old.isValid:
        old.deleteMe()
    if refresh:
        adsk.core.Application.get().activeViewport.refresh()

def screen_pos(vp):
    """Node positions on screen, cached until the camera or the nodes change (one API call per node, not per move)."""
    cam = vp.camera
    key = (tuple(round(c, 6) for c in cam.eye.asArray() + cam.target.asArray() + cam.upVector.asArray()),
           round(cam.viewExtents, 6), vp.width, vp.height)
    if _state['screen'][0] != key:
        sp = {}
        for i in _state['nodes']:
            v = vp.modelToViewSpace(adsk.core.Point3D.create(*_state['pts'][i]))
            sp[i] = (v.x, v.y)
        _state['screen'] = (key, sp)
    return _state['screen'][1]

def corner_at(args, skip=None):
    """Node under the mouse (within the snap radius in pixels), else None."""
    if not _state['body'] or not _state['nodes']:
        return None
    pos, r = args.viewportPosition, _state['inputs'].itemById('snappx').valueOne
    best = None
    for i, (x, y) in screen_pos(args.viewport).items():
        if i != skip:
            d = ((x - pos.x)**2 + (y - pos.y)**2) ** 0.5
            if d <= r and (best is None or d < best[0]):
                best = (d, i)
    return best and best[1]

def redraw():
    if _state['body']:
        draw(_state['body'].parentComponent, refresh=False)
    draw_ghost()  # refreshes once for both

def hover(args):
    """Throttled: tiny or too-frequent moves are skipped (each update costs a ray cast + a redraw)."""
    pos = args.viewportPosition
    t, last = _state['last_move']
    now = time.perf_counter()
    if last and abs(pos.x - last[0]) + abs(pos.y - last[1]) < 3 and now - t < 0.25:
        return
    if now - t < 0.03:
        return
    _state['last_move'] = (now, (pos.x, pos.y))
    if mode() == 'Pausa':
        if _state['ghost']:
            _state['ghost'] = None; draw_ghost()
        return
    h = corner_at(args)
    if h != _state['hover']:
        _state['hover'] = h
        if _state['body']:
            draw(_state['body'].parentComponent, refresh=False)
    update_ghost(args)  # one viewport refresh for both groups

def drag_begin(args):
    _state['grab'] = corner_at(args) if mode() == 'Pontos' else None

def drag(args):
    """Pontos mode: the grabbed node follows the mouse over the mesh (throttled)."""
    i = _state['grab']
    if i is None:
        return
    now = time.perf_counter()
    if now - _state['last_move'][0] < 0.05:
        return
    _state['last_move'] = (now, None)
    update_ghost(args, skip=i)
    g = _state['ghost']
    if g and g[0] == _state['body']:
        if not _state['history'] or _state['history'][-1][:2] != ('move', i):
            _state['history'].append(('move', i, _state['pts'][i]))
        _state['pts'][i] = g[1]
        _state['screen'] = (None, {})
        draw(_state['body'].parentComponent)

def drag_end(args):
    if _state['grab'] is not None:
        _state['grab'] = None
        status()
        redraw()

def build(inputs):
    """OK: the real sketch (all lines) inside the 'IgorSurface' group."""
    body = _state['body']
    if not body or not _state['edges']:
        return
    restore_opacity()
    comp = body.parentComponent
    pts, edges = _state['pts'], _state['edges']
    grp = next((o.component for o in comp.occurrences if o.component.name == 'IgorSurface'), None)
    if grp is None:
        grp = comp.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        grp.name = 'IgorSurface'
    sk = grp.sketches.add(grp.xYConstructionPlane)
    sk.name = 'Perímetros %d' % grp.sketches.count
    sk.isComputeDeferred = True
    used = {i for e in edges for i in e}
    node = {i: sk.sketchPoints.add(sk.modelToSketchSpace(adsk.core.Point3D.create(*pts[i]))) for i in used}
    for a, b in edges:
        sk.sketchCurves.sketchLines.addByTwoPoints(node[a], node[b])
    sk.isComputeDeferred = False  # sketch only: lighter than patches (Igor, 2026-10-29)
