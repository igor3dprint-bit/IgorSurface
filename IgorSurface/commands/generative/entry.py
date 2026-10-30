"""Estrutura Generativa: the user clicks where the part is held and where the force goes; an optimized truss
(lib/truss.py) is drawn as a sketch and turned into printable round bars, each sized by its real force."""
import adsk.core, adsk.fusion
from ...lib import ui, truss

CMD_ID = 'IgorSurface_generative'
DIRS = (('Para baixo (-Z)', (0, 0, -1)), ('Para cima (+Z)', (0, 0, 1)), ('-X', (-1, 0, 0)), ('+X', (1, 0, 0)),
        ('-Y', (0, -1, 0)), ('+Y', (0, 1, 0)))
PICK = ('Faces', 'Edges', 'Vertices', 'SketchPoints', 'ConstructionPoints', 'MeshBodies', 'Bodies')


def start():
    ui.add_command(CMD_ID, 'Estrutura Generativa',
                   'Clique onde a peça fica presa e onde a força é aplicada: o plugin calcula uma treliça otimizada '
                   '(barra só onde há esforço) e cria o esboço e as barras dimensionadas pela força.', created)


def stop():
    ui.remove_command(CMD_ID)


def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    fix = inputs.addSelectionInput('fix', 'Fixação', 'Clique nos pontos onde a peça fica presa (2 ou mais)')
    fix.setSelectionLimits(1, 0)
    load = inputs.addSelectionInput('load', 'Força em', 'Clique no ponto onde a força é aplicada')
    load.setSelectionLimits(1, 1)
    for s in (fix, load):
        for f in PICK:
            s.addSelectionFilter(f)
    dd = inputs.addDropDownCommandInput('dir', 'Direção', adsk.core.DropDownStyles.TextListDropDownStyle)
    for i, (name, _) in enumerate(DIRS):
        dd.listItems.add(name, i == 0)
    inputs.addFloatSpinnerCommandInput('force', 'Força (N)', '', 1, 1e6, 10, 100)
    st = inputs.addFloatSpinnerCommandInput('stress', 'Tensão (MPa)', '', 1, 1000, 1, 15)
    st.tooltip = 'Tensão admissível do material, já com segurança. PLA ~15, PETG ~12, ABS ~12, aço ~100.'
    inputs.addValueInput('dmin', 'Barra mín.', 'mm', adsk.core.ValueInput.createByString('2 mm'))
    r = inputs.addIntegerSliderCommandInput('res', 'Resolução', 3, 8)
    r.valueOne = 5
    r.tooltip = 'Pontos da grade no lado maior. Mais = estrutura mais fina e cálculo mais lento.'
    inputs.addTextBoxCommandInput('info', 'Status', '1) Fixação: clique onde a peça fica presa. 2) Clique no campo Força em e no ponto da força.', 3, True)
    cmd.okButtonText = 'Gerar'
    ui.on(('validate', cmd.validateInputs), lambda a: setattr(a, 'areInputsValid',
          inputs.itemById('fix').selectionCount >= 1 and inputs.itemById('load').selectionCount == 1))
    ui.on(('command', cmd.execute), lambda a: run(a, inputs))


def run(args, inputs):
    fix, load = inputs.itemById('fix'), inputs.itemById('load')
    P = lambda s: (s.point.x, s.point.y, s.point.z)  # where it was clicked, world cm
    supports = [P(fix.selection(i)) for i in range(fix.selectionCount)]
    lp = P(load.selection(0))
    mag = inputs.itemById('force').value
    d = DIRS[inputs.itemById('dir').selectedItem.index][1]
    pb = ui.ui.progressBar
    pb.show('Estrutura Generativa: %p%', 0, 100, False)
    try:
        bars = truss.design(supports, lp, tuple(mag*c for c in d), inputs.itemById('stress').value * 100,  # MPa -> N/cm^2
                            inputs.itemById('dmin').value, inputs.itemById('res').valueOne,
                            lambda i, n: (setattr(pb, 'progressValue', int(80*i/n)), adsk.doEvents()))
        if not bars:
            raise ValueError('nenhuma barra sobrou; afaste a força da fixação')
        build(bars, lambda v: (setattr(pb, 'progressValue', v), adsk.doEvents()))
        ui.app.log('Estrutura Generativa: %d barras, força máx %.0f N.' % (len(bars), max(abs(b[3]) for b in bars)))
    except Exception as exc:
        args.executeFailed = True
        args.executeFailedMessage = 'Não deu para gerar a estrutura: %s' % exc
    finally:
        pb.hide()


def build(bars, progress):
    root = adsk.fusion.Design.cast(ui.app.activeProduct).rootComponent
    grp = next((o.component for o in root.occurrences if o.component.name == 'IgorSurface'), None)
    if grp is None:
        grp = root.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        grp.name = 'IgorSurface'
    n = 1 + sum(1 for s in grp.sketches if s.name.startswith('Estrutura '))
    sk = grp.sketches.add(grp.xYConstructionPlane)
    sk.name = 'Estrutura %d' % n
    sk.isComputeDeferred = True
    pts, lines = {}, []
    node = lambda p: pts.get(p) or pts.setdefault(p, sk.sketchPoints.add(sk.modelToSketchSpace(adsk.core.Point3D.create(*p))))
    for p0, p1, dia, _ in bars:
        lines.append((sk.sketchCurves.sketchLines.addByTwoPoints(node(p0), node(p1)), dia))
    sk.isComputeDeferred = False
    pf = grp.features.pipeFeatures
    bodies = []
    for k, (ln, dia) in enumerate(lines):
        inp = pf.createInput(grp.features.createPath(ln, False), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        inp.sectionSize = adsk.core.ValueInput.createByReal(dia)
        bodies += list(pf.add(inp).bodies)
        progress(80 + int(15*k/len(lines)))
    # ponytail: joints are plain overlapping pipe ends; add node spheres if the corners print badly
    tools = adsk.core.ObjectCollection.create()
    for b in bodies[1:]:
        tools.add(b)
    if tools.count:
        cf = grp.features.combineFeatures
        ci = cf.createInput(bodies[0], tools)
        ci.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
        cf.add(ci)
    bodies[0].name = 'Estrutura %d' % n
