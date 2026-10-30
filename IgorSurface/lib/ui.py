"""Tiny Fusion UI plumbing shared by the commands: handler refs, toolbar placement, error reporting."""
import os, traceback
import adsk.core

app = adsk.core.Application.get()
ui = app.userInterface
_handlers = []  # Fusion drops handlers that Python garbage-collects

PANEL_ID = 'IgorSurfacePanel'
CG_ID = 'IgorSurface'
TABS = ('SolidTab', 'SurfaceTab', 'ParaMeshOuterTab')
RES = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources')

def on(event, fn):
    """Subscribe fn(args) to a Fusion event, reporting exceptions instead of swallowing them."""
    base = {
        'commandCreated': adsk.core.CommandCreatedEventHandler,
        'command': adsk.core.CommandEventHandler,
        'inputChanged': adsk.core.InputChangedEventHandler,
        'validate': adsk.core.ValidateInputsEventHandler,
        'select': adsk.core.SelectionEventHandler,
        'mouse': adsk.core.MouseEventHandler,
        'keyboard': adsk.core.KeyboardEventHandler,
        'document': adsk.core.DocumentEventHandler,
    }[event[0]]

    class H(base):
        def notify(self, args):
            try:
                fn(args)
            except Exception:
                if event[0] in ('mouse', 'keyboard'):  # fires on every mouse move: a dialog here would lock Fusion
                    log()
                else:
                    error()
    h = H()
    event[1].add(h)
    _handlers.append(h)
    return h

LOG = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'IgorSurface', 'erros.log')

def log():
    import time
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + traceback.format_exc() + '\n')

def error(msg=None):
    ui.messageBox((msg or 'Erro inesperado') + '\n\n' + traceback.format_exc(), 'IgorSurface')

def panels():
    ws = ui.workspaces.itemById('FusionSolidEnvironment')
    out = []
    for tab_id in TABS:
        tab = ws.toolbarTabs.itemById(tab_id)
        if not tab:
            continue
        p = tab.toolbarPanels.itemById(PANEL_ID) or tab.toolbarPanels.add(PANEL_ID, 'IGOR SURFACE', '', False)
        out.append(p)
    return out

def add_command(cmd_id, name, tip, on_created, promote=False, dropdown=None):
    defs = ui.commandDefinitions
    remove_command(cmd_id)
    res = os.path.join(RES, cmd_id.split('_')[-1])
    # a definition Fusion refuses to delete (left by a reload) is reused instead of failing
    cd = defs.itemById(cmd_id) or defs.addButtonDefinition(cmd_id, name, tip, res if os.path.isdir(res) else '')
    cd.name, cd.tooltip = name, tip
    def created_once(args):  # a reused definition can carry stale handlers: build the dialog only once
        if args.command.commandInputs.count == 0:
            on_created(args)
    on(('commandCreated', cd.commandCreated), created_once)
    for p in panels():
        holder = p.controls
        if dropdown:  # group related tools under one menu button
            dd_id = 'IgorSurface_dd_' + dropdown
            dd = holder.itemById(dd_id) or holder.addDropDown(dropdown, os.path.join(RES, 'dd_' + dropdown.lower()) if os.path.isdir(os.path.join(RES, 'dd_' + dropdown.lower())) else '', dd_id)
            holder = dd.controls
        stale = holder.itemById(cmd_id)
        if stale:
            stale.deleteMe()
        c = holder.addCommand(cd)
        c.isPromoted = c.isPromotedByDefault = promote
    return cd

def remove_command(cmd_id):
    for p in panels():
        c = p.controls.itemById(cmd_id)
        for i in range(p.controls.count):  # also look inside our dropdown menus
            dd = adsk.core.DropDownControl.cast(p.controls.item(i))
            if not c and dd and dd.id.startswith('IgorSurface_dd_'):
                c = dd.controls.itemById(cmd_id)
        if c:
            c.deleteMe()
    for _ in range(10):  # earlier reloads can leave duplicates behind
        cd = ui.commandDefinitions.itemById(cmd_id)
        if not cd:
            break
        cd.deleteMe()

def remove_panels():
    for p in panels():
        if not p.isValid:
            continue
        for i in range(p.controls.count - 1, -1, -1):
            dd = adsk.core.DropDownControl.cast(p.controls.item(i))
            if dd and dd.id.startswith('IgorSurface_dd_') and dd.controls.count == 0:
                dd.deleteMe()
        if p.controls.count == 0:
            p.deleteMe()

def purge_graphics():
    """Remove IgorSurface graphics left in the active design (e.g. after a crash)."""
    d = app.activeProduct
    for comp in getattr(d, 'allComponents', []):
        gs = comp.customGraphicsGroups
        for i in range(gs.count - 1, -1, -1):
            if gs.item(i).id == CG_ID:
                gs.item(i).deleteMe()
