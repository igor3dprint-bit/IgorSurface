"""Freeform: turns the faces of a Malha Manual group (IgorSurface component) into one T-Spline (Form) body.
Faces are welded by corner position into a control cage; Fusion's Form smooths it."""
import adsk.core, adsk.fusion
from ...lib import ui
from . import tsm

CMD_ID = 'IgorSurface_freeform'
WELD = 1e-5  # cm: corners closer than this are the same cage vertex

def start():
    ui.add_command(CMD_ID, 'Freeform',
                   'Leva todas as faces do grupo IgorSurface escolhido para o Freeform (Form/T-Spline), '
                   'como uma malha suave e editável.', created)

def stop():
    ui.remove_command(CMD_ID)

def groups(design):
    return [o for o in design.rootComponent.allOccurrences if o.component.name.startswith('IgorSurface')]

def created(args):
    cmd = args.command
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput('group', 'Grupo', 'Escolha o grupo IgorSurface (no navegador ou clicando numa face dele)')
    sel.addSelectionFilter('Occurrences')
    sel.addSelectionFilter('SurfaceBodies')
    sel.setSelectionLimits(1, 1)
    design = adsk.fusion.Design.cast(ui.app.activeProduct)
    # preselect: whatever group was selected before opening, else the only group in the design
    pre = [s.entity for s in ui.ui.activeSelections if group_of(s.entity)]
    gs = groups(design) if design else []
    if pre:
        sel.addSelection(pre[0])
    elif len(gs) == 1:
        sel.addSelection(gs[0])
    inputs.addBoolValueInput('hide', 'Esconder as faces originais', True, '', True)
    ui.on(('validate', cmd.validateInputs), lambda a: setattr(a, 'areInputsValid', sel.selectionCount == 1 and group_of(sel.selection(0).entity) is not None))
    ui.on(('command', cmd.execute), lambda a: run(a, inputs))

def group_of(entity):
    """IgorSurface component for a picked occurrence or for one of its face bodies."""
    occ = adsk.fusion.Occurrence.cast(entity)
    if occ and occ.component.name.startswith('IgorSurface'):
        return occ.component
    body = adsk.fusion.BRepBody.cast(entity)
    if body and body.parentComponent.name.startswith('IgorSurface'):
        return body.parentComponent
    return None

def cage(comp):
    """(vertices, faces) welded from the group's Face bodies; faces are corner-index loops in edge order."""
    verts, index, faces = [], {}, []
    key = lambda p: (round(p.x / WELD), round(p.y / WELD), round(p.z / WELD))
    bodies = [b for b in comp.bRepBodies if b.name.startswith('Face ')]
    for b in bodies:
        face = b.faces.item(0)
        loop = face.loops.item(0)
        ids = []
        for coedge in loop.coEdges:
            e = coedge.edge
            v = e.endVertex if coedge.isOpposedToEdge else e.startVertex
            k = key(v.geometry)
            if k not in index:
                index[k] = len(verts)
                verts.append((v.geometry.x, v.geometry.y, v.geometry.z))
            ids.append(index[k])
        if len(ids) in (3, 4):
            faces.append(ids)
    return verts, faces, bodies

def orient(faces):
    """Flip faces so neighbours traverse their shared edge in opposite directions (patches come in any winding)."""
    owner = {}
    for fi, f in enumerate(faces):
        for k in range(len(f)):
            owner.setdefault(frozenset((f[k], f[(k+1) % len(f)])), []).append(fi)
    done = [False] * len(faces)
    for seed in range(len(faces)):
        if done[seed]:
            continue
        done[seed] = True
        stack = [seed]
        while stack:
            f = faces[stack.pop()]
            for k in range(len(f)):
                a, b = f[k], f[(k+1) % len(f)]
                for gi in owner[frozenset((a, b))]:
                    if done[gi]:
                        continue
                    g = faces[gi]
                    if any(g[j] == a and g[(j+1) % len(g)] == b for j in range(len(g))):
                        g.reverse()  # same direction as us: flip
                    done[gi] = True
                    stack.append(gi)
    return faces

def run(args, inputs):
    comp = group_of(inputs.itemById('group').selection(0).entity)
    verts, faces, bodies = cage(comp)
    orient(faces)
    if not faces:
        ui.ui.messageBox('Esse grupo não tem faces da Malha Manual.', 'Freeform')
        args.executeFailed = True
        return
    ff = comp.features.formFeatures.add()
    ff.startEdit()
    body = ff.tSplineBodies.addByTSMDescription(tsm.write(verts, faces))
    ff.finishEdit()
    if not body:
        raise RuntimeError('O Fusion recusou a malha (TSM inválido).')
    if inputs.itemById('hide').value:
        for b in bodies:
            b.isLightBulbOn = False
