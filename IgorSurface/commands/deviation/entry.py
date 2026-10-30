"""Mapa de Desvio: colors the scan by its distance to the CAD (surfaces/solids made from it).
Green = within tolerance, yellow->red = scan outside the CAD, cyan->blue = scan inside."""
import math
import adsk.core, adsk.fusion
from ...lib import ui, region
from ..fitSurface.entry import mesh_of, reset_cache_check

CMD_ID = 'IgorSurface_deviation'
MAX_PTS = 60000  # ponytail: pure-Python closest-point; bigger scans are subsampled (stride) for the stats
_shown = []      # overlay groups; they live only while the dialog is open
_calc = {}       # last computed map: body, scan, dist, tol, rng, text

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
    go = inputs.addBoolValueInput('go', 'Calcular', False, '', False)
    go.tooltip = 'Calcula e pinta a malha. O mapa some quando a janela fecha.'
    inputs.addTextBoxCommandInput('info', 'Resultado', 'Escolha a malha e o CAD e clique em Calcular.', 4, True)
    cmd.okButtonText = 'Fechar'
    _calc.clear()
    # the map is drawn in the preview: Fusion rolls preview graphics back on every input change and when the
    # dialog closes, so the map is visible only while the tool is open (Igor, 2026-10-30)
    ui.on(('inputChanged', cmd.inputChanged), lambda a: a.input.id == 'go' and calc(inputs))
    ui.on(('validate', cmd.validateInputs), lambda a: setattr(a, 'areInputsValid', True))
    ui.on(('command', cmd.executePreview), lambda a: show())
    ui.on(('command', cmd.destroy), lambda a: clear())
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

def calc(inputs):
    inputs.itemById('go').value = False
    info = inputs.itemById('info')
    if inputs.itemById('mesh').selectionCount != 1 or inputs.itemById('bodies').selectionCount < 1:
        info.text = 'Escolha a malha e pelo menos um corpo CAD.'
        return
    mesh_body = adsk.fusion.MeshBody.cast(inputs.itemById('mesh').selection(0).entity)
    sel = inputs.itemById('bodies')
    bodies = [adsk.fusion.BRepBody.cast(sel.selection(i).entity) for i in range(sel.selectionCount)]
    tol, rng = inputs.itemById('tol').value, inputs.itemById('rng').value
    scan = mesh_of(mesh_body)
    ref = reference(bodies)
    if not ref.t or not scan.v:
        info.text = 'Não deu para medir: corpo ou malha sem triângulos.'
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
    info.text = ('Dentro de ±%.2f mm: %.1f%%\nRMS: %.3f mm\nMáx para fora: %.3f mm\nMáx para dentro: %.3f mm'
                 % (tol*10, inside*100, rms*10, max(sample)*10, -min(sample)*10))
    _calc.update(body=mesh_body, scan=scan, dist=dist, tol=tol, rng=rng)

def show():
    """Overlay: the scan's own triangles, vertex-colored; the scan is hidden meanwhile (both undone on close)."""
    clear()
    if not _calc or not _calc['body'].isValid:
        return
    scan, dist, body = _calc['scan'], _calc['dist'], _calc['body']
    coords = adsk.fusion.CustomGraphicsCoordinates.create([c for p in scan.v for c in p])
    coords.colors = [c for d in dist for c in region.heat(d, _calc['tol'], _calc['rng'])]
    g = body.parentComponent.customGraphicsGroups.add()
    g.id = ui.CG_ID + '_desvio'
    gm = g.addMesh(coords, [i for t in scan.t for i in t], [], [])
    gm.color = adsk.fusion.CustomGraphicsVertexColorEffect.create()
    gm.depthPriority = 1
    _shown.append((g, body))
    body.isLightBulbOn = False
