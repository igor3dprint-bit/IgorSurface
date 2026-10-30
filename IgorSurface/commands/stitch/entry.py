"""Stitch to Solid: stitch the picked surfaces (Malha Manual faces come preselected) into a solid."""
import adsk.core, adsk.fusion
from ...lib import ui

CMD_ID = 'IgorSurface_stitch'

def start():
    ui.add_command(CMD_ID, 'Costurar em Sólido',
                   'Costura as superfícies escolhidas num sólido. As superfícies precisam se encostar '
                   '(use Extend/Trim antes se tiver fresta).',
                   created, promote=True)

def stop():
    ui.remove_command(CMD_ID)

def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput('bodies', 'Superfícies', 'Escolha as superfícies a costurar')
    sel.addSelectionFilter('SurfaceBodies')
    sel.setSelectionLimits(1, 0)
    inputs.addValueInput('tol', 'Tolerância', 'mm', adsk.core.ValueInput.createByString('0.1 mm'))
    design = adsk.fusion.Design.cast(ui.app.activeProduct)
    # the Malha Manual faces come preselected; selections must be the occurrence's proxies
    for occ in (design.rootComponent.allOccurrences if design else []):
        if occ.component.name == 'IgorSurface':
            for b in occ.bRepBodies:
                if not b.isSolid and b.isVisible:
                    sel.addSelection(b)
    ui.on(('command', cmd.execute), lambda a: run(a, inputs))

def run(args, inputs):
    sel = inputs.itemById('bodies')
    bodies = adsk.core.ObjectCollection.create()
    for i in range(sel.selectionCount):
        e = sel.selection(i).entity
        bodies.add(e.nativeObject or e)  # the feature lives in the component: proxies make it fail
    comp = bodies.item(0).parentComponent
    st = comp.features.stitchFeatures
    inp = st.createInput(bodies, adsk.core.ValueInput.createByReal(inputs.itemById('tol').value),
                         adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    try:
        f = st.add(inp)
    except RuntimeError as e:
        ui.ui.messageBox('Não costurou: as superfícies não fecham dentro da tolerância.\n\n%s' % e, 'IgorSurface')
        args.executeFailed = True
        return
    solid = any(f.bodies.item(i).isSolid for i in range(f.bodies.count))
    if not solid:
        ui.ui.messageBox('Costurou, mas ainda ficou aberto (superfície, não sólido). Feche as frestas e tente de novo.', 'IgorSurface')
    else:
        f.bodies.item(0).name = 'Sólido IgorSurface'
