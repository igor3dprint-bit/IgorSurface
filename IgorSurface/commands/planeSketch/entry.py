"""Fit Plane -> Sketch: click a flat area, get a sketch on the fitted plane with the mesh cross-section."""
import adsk.core, adsk.fusion
from ...lib import ui, region, build
from ..fitSurface.entry import mesh_of, to_component, reset_cache_check

CMD_ID = 'IgorSurface_planeSketch'
_state = {}

def start():
    ui.add_command(CMD_ID, 'Plano → Esboço',
                   'Clique numa área plana da malha: cria plano ajustado + esboço com o corte da malha '
                   '(deslocado para dentro do material) pronto para extrudar.',
                   created)

def stop():
    ui.remove_command(CMD_ID)

def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput('pick', 'Ponto', 'Clique numa área plana da malha')
    sel.addSelectionFilter('MeshBodies')
    sel.setSelectionLimits(1, 1)
    inputs.addValueInput('offset', 'Profund.', 'mm', adsk.core.ValueInput.createByString('0.2 mm'))
    inputs.addIntegerSpinnerCommandInput('count', 'Cortes', 1, 100, 1, 1)
    inputs.addValueInput('step', 'Passo', 'mm', adsk.core.ValueInput.createByString('5 mm'))
    inputs.addBoolValueInput('clean', 'Limpo', True, '', True)
    inputs.addValueInput('ctol', 'Tol.', 'mm', adsk.core.ValueInput.createByString('0.05 mm'))
    inputs.addTextBoxCommandInput('info', 'Ajuste', 'Clique na malha.', 3, True)
    _state.clear()
    reset_cache_check()
    ui.on(('select', cmd.select), lambda a: _state.update(body=adsk.fusion.MeshBody.cast(a.selection.entity), p=a.selection.point))
    ui.on(('command', cmd.execute), lambda a: run(a, inputs))

def run(args, inputs):
    body = _state.get('body')
    if not body:
        return
    mesh = mesh_of(body)
    model, tris = region.detect(mesh, [mesh.nearest_tri(to_component(body, _state['p']))], 'plane')
    if model is None or model.max > 0.05:  # > 0.5 mm off a plane is not a flat face
        ui.ui.messageBox('Essa área não é plana (desvio %.3f mm). Clique numa face plana.' % ((model.max if model else 0)*10), 'IgorSurface')
        args.executeFailed = True
        return
    # the fitted normal points out of the material when the region's facets agree with it
    if sum(region.dot(mesh.nrm[t], model.n) for t in tris) > 0:
        model.n = tuple(-x for x in model.n)
    comp = body.parentComponent
    n = 1 + sum(1 for s in comp.sketches if s.name.startswith('Corte '))
    tol = inputs.itemById('ctol').value if inputs.itemById('clean').value else None
    off, step = inputs.itemById('offset').value, inputs.itemById('step').value
    segs = 0
    for k in range(inputs.itemById('count').value):  # series go deeper into the material
        segs += build.section(comp, model, mesh, off + k*step, 'Corte %d' % (n + k), tol)
    if segs == 0:
        ui.ui.messageBox('O plano não cortou a malha. Aumente "Corte para dentro".', 'IgorSurface')
