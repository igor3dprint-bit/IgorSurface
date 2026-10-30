"""IgorOrganizer: one click puts every loose body (solid, surface, STL/mesh, STEP import...) into its own
component named after the body. Sketches stay where they are; the IgorSurface group is left intact."""
import adsk.core, adsk.fusion
from ...lib import ui

CMD_ID = 'IgorSurface_organize'
KEEP = ('IgorSurface',)  # groups that must stay together

def start():
    ui.add_command(CMD_ID, 'IgorOrganizer',
                   'Organiza o projeto num clique: cada sólido, superfície ou malha (STL, STEP...) solto vira '
                   'um componente com o nome dele. Esboços ficam onde estão.', created)

def stop():
    ui.remove_command(CMD_ID)

def created(args):
    # no inputs: Fusion runs execute right away, as one undo step
    ui.on(('command', args.command.execute), run)

def run(args):
    design = adsk.fusion.Design.cast(ui.app.activeProduct)
    if not design:
        ui.ui.messageBox('Abra um projeto de design primeiro.', 'IgorOrganizer')
        return
    moved, failed = 0, []
    linked = {o.component.id for o in design.rootComponent.allOccurrences if o.isReferencedComponent}
    for comp in list(design.allComponents):
        if comp.name in KEEP or comp.id in linked:
            continue
        bodies = list(comp.bRepBodies) + list(comp.meshBodies)
        # a component that already holds exactly one body (and isn't the root) is organized
        if comp != design.rootComponent and len(bodies) <= 1:
            continue
        for b in bodies:
            name = b.name
            try:
                nb = b.createComponent()
                nb.parentComponent.name = name
                moved += 1
            except RuntimeError:
                failed.append(name)
    msg = '%d corpo(s) separados em componentes.' % moved if moved else 'Já estava organizado.'
    if failed:
        msg += '\n\nNão deu para mover: ' + ', '.join(failed)
    ui.ui.messageBox(msg, 'IgorOrganizer')
