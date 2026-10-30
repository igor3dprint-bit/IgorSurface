"""CriarAuto: each click on the mesh grows one face (plane, cylinder, sphere, cone) from that spot and shows it;
clicking a shown face again drops it. OK draws only sketches (lighter than surfaces) in the IgorSurface group:
plane = its real border (holes included), cylinder = both rims."""
import adsk.core, adsk.fusion
from ...lib import ui, region, build
from ..fitSurface.entry import mesh_of, to_component, reset_cache_check, NAMES

CMD_ID = 'IgorSurface_autoSurface'
COLORS = ((243, 156, 18), (47, 143, 216), (39, 174, 96), (155, 89, 182))
_state = {}


def start():
    ui.add_command(CMD_ID, 'CriarAuto Superfície',
                   'Clique numa face da malha: só aquela face é reconhecida (plano, cilindro...) e fica destacada. '
                   'Clique em outras para somar; clique de novo numa destacada para tirar. OK cria os esboços.', created)


def stop():
    ui.remove_command(CMD_ID)


def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput('mesh', 'Faces', 'Clique nas faces da malha')
    sel.addSelectionFilter('MeshBodies')
    sel.setSelectionLimits(0, 0)
    tol = inputs.addValueInput('tol', 'Tol.', 'mm', adsk.core.ValueInput.createByString('0.05 mm'))
    tol.tooltip = 'Quanto a malha pode fugir da forma ideal e ainda contar como a mesma face.'
    u = inputs.addBoolValueInput('undo', 'Desfazer', False, '', False)
    u.tooltip = 'Tira a última face.'
    inputs.addTextBoxCommandInput('info', 'Status', 'Clique numa face da malha.', 3, True)
    cmd.okButtonText = 'Criar esboços'
    _state.clear()
    _state.update(body=None, faces=[], cg=None, inputs=inputs)  # faces: [(model, tris)]
    reset_cache_check()
    ui.on(('select', cmd.select), pick)
    ui.on(('select', cmd.unselect), pick)  # clicking the same body again is another face
    ui.on(('inputChanged', cmd.inputChanged), changed)
    ui.on(('validate', cmd.validateInputs), lambda a: setattr(a, 'areInputsValid', bool(_state['faces'])))
    ui.on(('command', cmd.execute), lambda a: run(a))
    ui.on(('command', cmd.destroy), lambda a: clear_graphics())


def pick(args):
    s = args.selection
    body = adsk.fusion.MeshBody.cast(s.entity)
    if not body:
        return
    if _state['body'] != body:
        _state['faces'].clear()  # new mesh -> start over
    _state['body'] = body
    mesh = mesh_of(body)
    seed = mesh.nearest_tri(to_component(body, s.point))
    hit = next((f for f in _state['faces'] if seed in f[1]), None)
    if hit:
        _state['faces'].remove(hit)
        status('Face tirada.')
    else:
        model, tris = region.detect(mesh, [seed], 'auto', dist_tol=_state['inputs'].itemById('tol').value, strict=True)
        if model is None:
            status('Não reconheci uma forma aqui. Tente outro ponto ou aumente a Tol.')
        else:
            _state['faces'].append((model, set(tris)))
            status('%s: RMS %.3f mm, %d triângulos.' % (NAMES[model.kind], model.rms*10, len(tris)))
    draw(body.parentComponent, mesh)


def status(last=''):
    kinds = [NAMES[m.kind] for m, _ in _state['faces']]
    head = '%d face(s)%s' % (len(kinds), ': ' + ', '.join(kinds) if kinds else '')
    _state['inputs'].itemById('info').text = head + ('\n' + last if last else '')


def changed(args):
    if args.input.id == 'undo':
        args.input.value = False
        if _state['faces']:
            _state['faces'].pop()
            status()
            draw(_state['body'].parentComponent, mesh_of(_state['body']))


def clear_graphics():
    cg = _state.get('cg')
    if cg and cg.isValid:
        cg.deleteMe()
    _state['cg'] = None


def draw(comp, mesh):
    """Each chosen face lifted 0.02 mm over the mesh, one color per face. New group first, then drop the old (no flicker)."""
    old = _state.get('cg')
    g = comp.customGraphicsGroups.add()
    g.id = ui.CG_ID
    for k, (_, tris) in enumerate(_state['faces']):
        coords, idx = [], []
        for t in tris:
            n = mesh.nrm[t]
            for vi in mesh.t[t]:
                p = mesh.v[vi]
                coords += [p[0] + n[0]*0.002, p[1] + n[1]*0.002, p[2] + n[2]*0.002]
                idx.append(len(idx))
        m = g.addMesh(adsk.fusion.CustomGraphicsCoordinates.create(coords), idx, [], [])
        m.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*COLORS[k % len(COLORS)], 255))
    _state['cg'] = g
    if old and old.isValid:
        old.deleteMe()
    adsk.core.Application.get().activeViewport.refresh()


def run(args):
    body = _state['body']
    if not body or not _state['faces']:
        return
    failed = sketch_faces(body, _state['faces'])
    if failed:
        ui.ui.messageBox('Algumas faces não viraram esboço:\n' + '\n'.join(failed), 'CriarAuto Superfície')


def sketch_faces(body, faces):
    """Sketches for [(model, tris)] in the IgorSurface group of the body's component. Returns failure texts."""
    mesh = mesh_of(body)
    comp = body.parentComponent
    grp = next((o.component for o in comp.occurrences if o.component.name == 'IgorSurface'), None)
    if grp is None:
        grp = comp.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        grp.name = 'IgorSurface'
    failed = []
    for model, tris in faces:
        tris = list(tris)
        verts, _, _ = mesh.region_data(tris)
        loops = [[mesh.v[i] for i in lp] for lp in region.boundary_loops(mesh, tris)] if model.kind == 'plane' else None
        n = 1 + sum(1 for s in grp.sketches if s.name.startswith(NAMES[model.kind] + ' ') and not s.name.endswith('_ref'))
        try:
            build.build(grp, model, verts, '%s %d' % (NAMES[model.kind], n), 'sketch', loops)
        except Exception as exc:
            failed.append('%s: %s' % (NAMES[model.kind], exc))
    return failed
