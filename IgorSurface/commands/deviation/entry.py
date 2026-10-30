"""Mapa de Desvio: colors the scan by its distance to the CAD (surfaces/solids made from it).
Green = within tolerance, yellow->red = scan outside the CAD, cyan->blue = scan inside."""
import math
import adsk.core, adsk.fusion
from ...lib import ui, region
from ..fitSurface.entry import mesh_of, reset_cache_check

CMD_ID = 'IgorSurface_deviation'
MAX_PTS = 60000  # ponytail: pure-Python closest-point; bigger scans are subsampled (stride) for the stats
_shown = []      # the colored overlay stays visible after OK; the next run replaces it

def start():
    ui.add_command(CMD_ID, 'Mapa de Desvio',
                   'Pinta a malha pela distância até as superfícies/sólidos: verde = dentro da tolerância, '
                   'vermelho = malha para fora, azul = malha para dentro. Mostra RMS e desvio máximo.', created)

def stop():
    clear()
    ui.remove_command(CMD_ID)

def clear():
    for g, mesh in _shown:
        if g.isValid:
            g.deleteMe()
        if mesh.isValid:
            mesh.isLightBulbOn = True  # the overlay replaced it while shown
    _shown.clear()

def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    m = inputs.addSelectionInput('mesh', 'Malha', 'A malha original (STL/scan)')
    m.addSelectionFilter('MeshBodies'); m.setSelectionLimits(1, 1)
    b = inputs.addSelectionInput('bodies', 'CAD', 'O CAD feito a partir dela')
    b.addSelectionFilter('Bodies'); b.setSelectionLimits(1, 0)
    for s in ui.ui.activeSelections:  # keep what the user had selected
        e = s.entity
        if adsk.fusion.MeshBody.cast(e) and m.selectionCount == 0:
            m.addSelection(e)
        elif adsk.fusion.BRepBody.cast(e):
            b.addSelection(e)
    inputs.addValueInput('tol', 'Verde até', 'mm', adsk.core.ValueInput.createByString('0.1 mm'))
    inputs.addValueInput('rng', 'Escala cor', 'mm', adsk.core.ValueInput.createByString('1 mm'))
    inputs.addBoolValueInput('off', 'Só limpar', True, '', False)
    cmd.okButtonText = 'Calcular'
    ui.on(('validate', cmd.validateInputs), lambda a: setattr(a, 'areInputsValid',
          inputs.itemById('off').value or (m.selectionCount == 1 and b.selectionCount >= 1)))
    ui.on(('command', cmd.execute), lambda a: run(inputs))
    reset_cache_check()

def reference(bodies):
    """One region.Mesh from the bodies' fine tessellation."""
    coords, idx = [], []
    for body in bodies:
        calc = body.meshManager.createMeshCalculator()
        calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.HighQualityTriangleMesh)
        tm = calc.calculate()
        base = len(coords) // 3
        coords += list(tm.nodeCoordinatesAsDouble)
        idx += [base + i for i in tm.nodeIndices]
    return region.Mesh(coords, idx)

def run(inputs):
    clear()
    if inputs.itemById('off').value:
        return
    mesh_body = adsk.fusion.MeshBody.cast(inputs.itemById('mesh').selection(0).entity)
    sel = inputs.itemById('bodies')
    bodies = [adsk.fusion.BRepBody.cast(sel.selection(i).entity) for i in range(sel.selectionCount)]
    tol, rng = inputs.itemById('tol').value, inputs.itemById('rng').value
    scan = mesh_of(mesh_body)
    ref = reference(bodies)
    if not ref.t or not scan.v:
        ui.ui.messageBox('Não deu para medir: corpo ou malha sem triângulos.', 'Mapa de Desvio')
        return
    stride = max(1, math.ceil(len(scan.v) / MAX_PTS))
    pb = ui.ui.progressBar
    pb.show('Calculando desvio... %p%', 0, len(scan.v), False)
    dist = [0.0] * len(scan.v)
    try:
        for i in range(0, len(scan.v), stride):
            dist[i] = region.deviation(ref, [scan.v[i]])[0]
            if stride > 1:  # fill the skipped vertices with the sampled value (display only)
                for k in range(i + 1, min(i + stride, len(scan.v))):
                    dist[k] = dist[i]
            if i % 2000 == 0:
                pb.progressValue = i
                adsk.doEvents()
    finally:
        pb.hide()
    sample = dist[::stride]
    inside = sum(1 for d in sample if abs(d) <= tol) / len(sample)
    rms = math.sqrt(sum(d*d for d in sample) / len(sample))
    # overlay: the scan's own triangles, vertex-colored; the scan is hidden meanwhile
    coords = adsk.fusion.CustomGraphicsCoordinates.create([c for p in scan.v for c in p])
    coords.colors = [c for d in dist for c in region.heat(d, tol, rng)]
    g = mesh_body.parentComponent.customGraphicsGroups.add()
    g.id = ui.CG_ID + '_desvio'
    gm = g.addMesh(coords, [i for t in scan.t for i in t], [], [])
    gm.color = adsk.fusion.CustomGraphicsVertexColorEffect.create()
    gm.depthPriority = 1
    _shown.append((g, mesh_body))
    mesh_body.isLightBulbOn = False
    ui.ui.messageBox('Dentro de ±%.2f mm: %.1f%%\nRMS: %.3f mm\nMáx para fora: %.3f mm\nMáx para dentro: %.3f mm\n\n'
                     'Para tirar o mapa: rode de novo com "Só limpar o mapa".'
                     % (tol*10, inside*100, rms*10, max(sample)*10, -min(sample)*10), 'Mapa de Desvio')
