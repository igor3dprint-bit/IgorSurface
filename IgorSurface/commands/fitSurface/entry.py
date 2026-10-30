"""Fit Surface: click on a mesh, region grows from the clicks, best primitive becomes an editable surface."""
import adsk.core, adsk.fusion
from ...lib import ui, region, build

CMD_ID = 'IgorSurface_fitSurface'
KINDS = [('auto', 'Automático'), ('plane', 'Plano'), ('cylinder', 'Cilindro'), ('sphere', 'Esfera'), ('cone', 'Cone')]
NAMES = {'plane': 'Plano', 'cylinder': 'Cilindro', 'sphere': 'Esfera', 'cone': 'Cone'}

_cache = {}   # mesh topology per body, rebuilt only when the mesh changes
_fresh = set()  # bodies already checked in the running command (body.mesh is costly: never per mouse move)

def reset_cache_check():
    _fresh.clear()
_state = {}   # per-command-run: picks, body, custom graphics

def start():
    ui.add_command(CMD_ID, 'Ajustar Superfície',
                   'Clique na malha: a região cresce a partir do clique e vira superfície CAD editável '
                   '(plano, cilindro, esfera ou cone). Mostra o erro do ajuste antes de confirmar.',
                   created, promote=True)

def stop():
    ui.remove_command(CMD_ID)

def mesh_of(body):
    """Cached region.Mesh for a MeshBody (component space)."""
    token = body.entityToken
    if token in _fresh:
        return _cache[token][1]
    pm = body.mesh
    key = (pm.nodeCount, pm.triangleCount)
    if _cache.get(token, (None,))[0] != key:
        idx = list(pm.triangleNodeIndices)
        q = pm.quadNodeIndices if pm.quadCount else ()
        for i in range(0, len(q), 4):  # quads -> 2 triangles
            idx += [q[i], q[i+1], q[i+2], q[i], q[i+2], q[i+3]]
        _cache.clear()
        _cache[token] = (key, region.Mesh(pm.nodeCoordinatesAsDouble, idx))
    _fresh.add(token)
    return _cache[token][1]

def to_component(body, p):
    """World click point -> body's component space (bodies inside occurrences)."""
    occ = body.assemblyContext
    if occ:
        m = occ.transform2.copy(); m.invert()
        p = p.copy(); p.transformBy(m)
    return (p.x, p.y, p.z)

def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput('picks', 'Pontos', 'Clique na malha (um ou mais pontos na mesma face)')
    sel.addSelectionFilter('MeshBodies')
    sel.setSelectionLimits(0, 0)
    dd = inputs.addDropDownCommandInput('kind', 'Tipo', adsk.core.DropDownStyles.TextListDropDownStyle)
    for k, label in KINDS:
        dd.listItems.add(label, k == 'auto')
    out = inputs.addDropDownCommandInput('output', 'Criar', adsk.core.DropDownStyles.TextListDropDownStyle)
    out.listItems.add('Superfície', True)
    out.listItems.add('Só construção (plano/eixo)', False)
    inputs.addValueInput('tol', 'Tol.', 'mm', adsk.core.ValueInput.createByString('0.05 mm'))
    inputs.addBoolValueInput('clear', 'Limpar', False, '', False)
    info = inputs.addTextBoxCommandInput('info', 'Ajuste', 'Clique na malha.', 4, True)
    info.isFullWidth = False
    _state.clear()
    _state.update(picks=[], body=None, cg=None, result=None)
    reset_cache_check()
    ui.on(('select', cmd.select), lambda a: pick(a, inputs))
    ui.on(('select', cmd.unselect), lambda a: pick(a, inputs))  # clicking the same body again still adds a pick
    ui.on(('inputChanged', cmd.inputChanged), changed)
    ui.on(('validate', cmd.validateInputs), lambda a: setattr(a, 'areInputsValid', bool(_state['picks'])))
    ui.on(('command', cmd.executePreview), lambda a: run(a, inputs, preview=True))
    ui.on(('command', cmd.execute), lambda a: run(a, inputs, preview=False))
    ui.on(('command', cmd.destroy), lambda a: clear_graphics())

def pick(args, inputs):
    s = args.selection
    body = adsk.fusion.MeshBody.cast(s.entity)
    if not body:
        return
    if _state['body'] and _state['body'] != body:
        _state['picks'].clear()  # new mesh -> start over
    _state['body'] = body
    _state['picks'].append(to_component(body, s.point))

def changed(args):
    if args.input.id == 'clear':
        _state['picks'].clear()
        args.inputs.itemById('picks').clearSelection()
        args.input.value = False
        args.inputs.itemById('info').text = 'Clique na malha.'
        clear_graphics()

def clear_graphics():
    cg = _state.get('cg')
    if cg and cg.isValid:
        cg.deleteMe()
    _state['cg'] = None

def highlight(comp, mesh, tris):
    clear_graphics()
    coords, idx = [], []
    for t in tris:
        for vi in mesh.t[t]:
            p = mesh.v[vi]; n = mesh.nrm[t]
            coords += [p[0] + n[0]*0.002, p[1] + n[1]*0.002, p[2] + n[2]*0.002]  # lift 0.02 mm over the mesh
            idx.append(len(idx))
    g = comp.customGraphicsGroups.add()
    m = g.addMesh(adsk.fusion.CustomGraphicsCoordinates.create(coords), idx, [], [])
    m.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(243, 156, 18, 255))
    _state['cg'] = g

def run(args, inputs, preview):
    info = inputs.itemById('info')
    body = _state['body']
    if not body or not _state['picks']:
        return
    kind = KINDS[[i.isSelected for i in inputs.itemById('kind').listItems].index(True)][0]
    surface = inputs.itemById('output').selectedItem.index == 0
    tol = inputs.itemById('tol').value  # cm
    mesh = mesh_of(body)
    seeds = list({mesh.nearest_tri(p) for p in _state['picks']})
    model, tris = region.detect(mesh, seeds, kind, dist_tol=tol)
    if model is None:
        info.text = 'Não deu para ajustar %s aqui. Clique em outra área ou troque o tipo.' % dict(KINDS)[kind].lower()
        args.executeFailed = True
        return
    comp = body.parentComponent
    verts, _, _ = mesh.region_data(list(tris))
    loops = [[mesh.v[i] for i in lp] for lp in region.boundary_loops(mesh, tris)] if model.kind == 'plane' else None
    n = 1 + sum(1 for b in comp.bRepBodies if b.name.startswith(NAMES[model.kind] + ' '))
    name = '%s %d' % (NAMES[model.kind], n)
    desc = build.build(comp, model, verts, name, surface, loops)
    info.text = '%s\nRMS %.4f mm | máx %.4f mm\n%d triângulos' % (desc, model.rms*10, model.max*10, len(tris))
    if preview:
        highlight(comp, mesh, tris)
