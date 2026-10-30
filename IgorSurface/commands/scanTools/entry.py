"""Scan workflow: Importar Scan (PLY/STL/OBJ/3MF), Preparar Scan, Alinhar Scan, Plano de Simetria."""
import os, tempfile
import adsk.core, adsk.fusion
from ...lib import ui, region, scan, build
from ...lib.fit import perp_basis
from ..fitSurface.entry import mesh_of, to_component, reset_cache_check

F = adsk.fusion
IDS = ('IgorSurface_importScan', 'IgorSurface_prepareScan', 'IgorSurface_alignScan', 'IgorSurface_symmetry')

def start():
    ui.add_command(IDS[0], 'Importar Scan', 'Importa malha de scanner: PLY (texto ou binário), STL, OBJ ou 3MF, em mm.', import_created, dropdown='Scan')
    ui.add_command(IDS[1], 'Preparar Scan', 'Um clique para limpar o scan: repara, apaga pedaços soltos, fecha furos e reduz triângulos.', prepare_created, dropdown='Scan')
    ui.add_command(IDS[2], 'Alinhar Scan', 'Clique no fundo da peça (vira o chão XY) e, se quiser, numa lateral ou furo (vira o eixo X). '
                   'A peça fica centralizada na origem.', align_created, dropdown='Scan')
    ui.add_command(IDS[3], 'Plano de Simetria', 'Acha o plano de espelho da peça e cria um plano de construção nele: '
                   'reconstrua metade e espelhe.', sym_created, dropdown='Scan')

def stop():
    for i in IDS:
        ui.remove_command(i)

def preselect(sel):
    for s in ui.ui.activeSelections:
        if F.MeshBody.cast(s.entity):
            sel.addSelection(s.entity)
            return

def mesh_input(inputs, name='Malha'):
    sel = inputs.addSelectionInput('mesh', name, 'Escolha a malha')
    sel.addSelectionFilter('MeshBodies'); sel.setSelectionLimits(1, 1)
    preselect(sel)
    return sel

def biggest_mesh(comp):
    ms = [m for m in comp.meshBodies if m.isLightBulbOn]
    return max(ms, key=lambda m: m.mesh.triangleCount) if ms else None

# ---------- Importar Scan ----------

def import_created(args):
    cmd = args.command
    ui.on(('command', cmd.execute), import_run)

def import_run(args):
    dlg = ui.ui.createFileDialog()
    dlg.title = 'Importar scan'
    dlg.filter = 'Scans (*.ply;*.stl;*.obj;*.3mf);;Todos (*.*)'
    if dlg.showOpen() != adsk.core.DialogResults.DialogOK:
        return
    path = dlg.filename
    design = F.Design.cast(ui.app.activeProduct)
    comp = design.rootComponent
    src = path
    if path.lower().endswith('.ply'):
        verts, faces = scan.read_ply(path)
        if not faces:
            ui.ui.messageBox('Esse PLY é só nuvem de pontos (sem faces). Gere a malha no software do scanner '
                             '(ou no MeshLab: Poisson) e importe de novo.', 'Importar Scan')
            return
        src = os.path.join(tempfile.mkdtemp(), os.path.splitext(os.path.basename(path))[0] + '.stl')
        scan.write_stl(src, verts, faces)
    bodies = comp.meshBodies.add(src, F.MeshUnits.MillimeterMeshUnit)
    for i in range(bodies.count):
        bodies.item(i).name = os.path.splitext(os.path.basename(path))[0]
    ui.app.activeViewport.fit()

# ---------- Preparar Scan ----------

def prepare_created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    mesh_input(inputs)
    inputs.addBoolValueInput('repair', 'Reparar', True, '', True)
    inputs.addBoolValueInput('shells', 'Tirar soltos', True, '', True)
    inputs.addBoolValueInput('holes', 'Fechar furos', True, '', False)
    inputs.addBoolValueInput('reduce', 'Reduzir', True, '', True)
    inputs.addIntegerSliderCommandInput('keep', 'Manter (%)', 5, 95).valueOne = 50
    cmd.okButtonText = 'Preparar'
    ui.on(('command', cmd.execute), lambda a: prepare_run(inputs))

def prepare_run(inputs):
    body = F.MeshBody.cast(inputs.itemById('mesh').selection(0).entity)
    name = body.name  # mesh features hand back renamed bodies
    comp = body.parentComponent
    feats = comp.features
    done, fails = [], []
    def step(label, fn):
        try:
            fn()
            done.append(label)
        except RuntimeError as e:
            fails.append('%s: %s' % (label, str(e).split('\n')[0]))
    cur = lambda: biggest_mesh(comp)
    if inputs.itemById('repair').value:
        def repair():
            i = feats.meshRepairFeatures.createInput(cur())
            i.meshRepairType = F.MeshRepairTypes.StitchAndRemoveMeshRepairType
            feats.meshRepairFeatures.add(i)
        step('reparado', repair)
    if inputs.itemById('shells').value:
        def shells():
            before = {m.entityToken for m in comp.meshBodies}
            i = feats.meshSeparateFeatures.createInput(cur())
            i.meshSeparateType = F.MeshSeparateTypes.ShellMeshSeparateType
            feats.meshSeparateFeatures.add(i)
            keep = cur()
            junk = [m for m in comp.meshBodies if m.isLightBulbOn and m != keep and m.entityToken not in before]
            if junk:
                feats.meshRemoveFeatures.add(feats.meshRemoveFeatures.createInput(junk))
            done.append('%d pedaço(s) apagado(s)' % len(junk))
        step('separado', shells)
    if inputs.itemById('holes').value:
        def holes():
            i = feats.meshRepairFeatures.createInput(cur())
            i.meshRepairType = F.MeshRepairTypes.CloseHolesMeshRepairType
            feats.meshRepairFeatures.add(i)
        step('furos fechados', holes)
    if inputs.itemById('reduce').value:
        def reduce():
            i = feats.meshReduceFeatures.createInput(cur())
            i.meshReduceTargetType = F.MeshReduceTargetTypes.ProportionMeshReduceTargetType
            i.proportion = adsk.core.ValueInput.createByReal(inputs.itemById('keep').valueOne)  # Fusion wants 0-100, not a fraction
            feats.meshReduceFeatures.add(i)
        step('reduzido', reduce)
    m = cur()
    if m:
        m.name = name
    msg = 'Feito: ' + ', '.join(done) + ('\nTriângulos agora: %d' % m.mesh.triangleCount if m else '')
    if fails:
        msg += '\n\nNão rolou:\n' + '\n'.join(fails)
    ui.ui.messageBox(msg, 'Preparar Scan')

# ---------- Alinhar Scan ----------

_align = {}

def align_created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    f = inputs.addSelectionInput('floor', 'Fundo (chão)', 'Clique na face de baixo da peça')
    f.addSelectionFilter('MeshBodies'); f.setSelectionLimits(1, 1)
    s = inputs.addSelectionInput('side', 'Eixo X (opcional)', 'Clique numa lateral plana ou num furo/cilindro')
    s.addSelectionFilter('MeshBodies'); s.setSelectionLimits(0, 1)
    inputs.addTextBoxCommandInput('info', '', 'Sem eixo X: usa a direção mais comprida da peça.', 2, True)
    cmd.okButtonText = 'Alinhar'
    _align.clear()
    reset_cache_check()
    ui.on(('select', cmd.select), lambda a: _align.__setitem__(a.activeInput.id, (F.MeshBody.cast(a.selection.entity), a.selection.point)))
    ui.on(('command', cmd.execute), lambda a: align_run(a))

def _fit_at(body, point, kind):
    mesh = mesh_of(body)
    return region.detect(mesh, [mesh.nearest_tri(to_component(body, point))], kind)[0]

def align_run(args):
    body, p = _align['floor']
    floor = _fit_at(body, p, 'plane')
    x_hint = None
    if 'side' in _align:
        m = _fit_at(*_align['side'], 'auto')
        x_hint = m.n if m.kind == 'plane' else getattr(m, 'axis', None)
    mesh = mesh_of(body)
    R, t = scan.frame(floor.origin, floor.n, mesh.v, x_hint)
    mat = adsk.core.Matrix3D.create()
    mat.setWithArray([R[0][0], R[0][1], R[0][2], t[0], R[1][0], R[1][1], R[1][2], t[1],
                      R[2][0], R[2][1], R[2][2], t[2], 0, 0, 0, 1])
    oc = adsk.core.ObjectCollection.create(); oc.add(body)
    mv = body.parentComponent.features.moveFeatures
    i = mv.createInput2(oc)
    i.defineAsFreeMove(mat)
    mv.add(i)
    ui.app.activeViewport.fit()

# ---------- Plano de Simetria ----------

def sym_created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    mesh_input(inputs)
    inputs.addTextBoxCommandInput('info', '', 'Leva alguns segundos em malha grande.', 1, True)
    cmd.okButtonText = 'Achar'
    reset_cache_check()
    ui.on(('command', cmd.execute), lambda a: sym_run(inputs))

def sym_run(inputs):
    body = F.MeshBody.cast(inputs.itemById('mesh').selection(0).entity)
    o, n, rms = scan.symmetry(mesh_of(body))
    u, v = perp_basis(n)
    pl, _, _ = build._ref_plane(body.parentComponent, o, u, v, 'Simetria')
    ui.ui.messageBox('Plano de simetria criado.\nErro médio do espelho: %.3f mm %s'
                     % (rms*10, '(peça simétrica)' if rms < 0.02 else '(simetria aproximada: confira)'), 'Plano de Simetria')
