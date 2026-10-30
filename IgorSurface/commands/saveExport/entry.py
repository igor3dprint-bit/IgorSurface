"""IgorSave: export the active design as .3mf + .f3d into a chosen folder; optionally quit Fusion
afterwards, and optionally do the same export automatically whenever a document closes."""
import os, re, json, signal
import adsk.core, adsk.fusion
from ...lib import ui

CMD_ID = 'IgorSurface_saveExport'
CFG = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'IgorSurface', 'igorsave.json')
_closing_handler = []

def load_cfg():
    try:
        with open(CFG, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'folder': os.path.join(os.path.expanduser('~'), 'Documents', 'IgorSave'), 'close': False, 'auto': False}

def save_cfg(cfg):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)

def start():
    cd = ui.add_command(CMD_ID, 'IgorSave',
                        'Salva o projeto como .3mf e .f3d na pasta escolhida. Pode fechar o Fusion depois '
                        'e pode salvar sozinho sempre que um projeto for fechado.', created)
    qat = ui.ui.toolbars.itemById('QAT')  # top bar, next to Fusion's own save
    if qat and not qat.controls.itemById(CMD_ID):
        try:
            qat.controls.addCommand(cd, 'SaveCommand', False)
        except RuntimeError:
            qat.controls.addCommand(cd)  # Fusion renamed its save button: just append
    h = adsk.core.DocumentEventHandler
    class Closing(h):
        def notify(self, args):
            on_closing(args)
    _closing_handler.append(Closing())
    ui.app.documentClosing.add(_closing_handler[-1])

def stop():
    qat = ui.ui.toolbars.itemById('QAT')
    c = qat and qat.controls.itemById(CMD_ID)
    if c:
        c.deleteMe()
    for h in _closing_handler:
        ui.app.documentClosing.remove(h)
    _closing_handler.clear()
    ui.remove_command(CMD_ID)

def created(args):
    cfg = load_cfg()
    inputs = args.command.commandInputs
    folder = inputs.addStringValueInput('folder', 'Pasta', cfg['folder'])
    folder.isReadOnly = True
    inputs.addBoolValueInput('pick', 'Escolher pasta…', False, '', False)
    inputs.addBoolValueInput('close', 'Fechar Fusion depois de salvar', True, '', cfg['close'])
    inputs.addBoolValueInput('auto', 'Automático: salvar ao fechar o projeto', True, '', cfg['auto'])
    inputs.addTextBoxCommandInput('info', '', 'Salva &lt;nome&gt;.3mf e &lt;nome&gt;.f3d', 1, True)
    args.command.okButtonText = 'Salvar'
    ui.on(('inputChanged', args.command.inputChanged), changed)
    ui.on(('command', args.command.execute), lambda a: run(a, inputs))

def changed(args):
    if args.input.id != 'pick':
        return
    args.input.value = False
    dlg = ui.ui.createFolderDialog()
    dlg.title = 'Onde salvar o 3MF e o F3D?'
    dlg.initialDirectory = args.inputs.itemById('folder').value
    if dlg.showDialog() == adsk.core.DialogResults.DialogOK:
        args.inputs.itemById('folder').value = dlg.folder

def export(doc, folder):
    """Writes <doc>.3mf and <doc>.f3d into folder. Returns the two paths."""
    design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
    if not design:
        raise RuntimeError('O documento "%s" não é um projeto de design.' % doc.name)
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, re.sub(r'[<>:"/\\|?*]+', '_', doc.name).strip() or 'projeto')
    em = design.exportManager
    paths = (base + '.3mf', base + '.f3d')
    em.execute(em.createC3MFExportOptions(design.rootComponent, paths[0]))
    em.execute(em.createFusionArchiveExportOptions(paths[1], design.rootComponent))
    return paths

def run(args, inputs):
    cfg = {'folder': inputs.itemById('folder').value,
           'close': inputs.itemById('close').value,
           'auto': inputs.itemById('auto').value}
    save_cfg(cfg)
    paths = export(ui.app.activeDocument, cfg['folder'])
    if cfg['close']:
        # ponytail: the API has no "quit"; files are already written, so end the process.
        # Unsaved cloud changes are NOT kept (the .f3d just written has them).
        os.kill(os.getpid(), signal.SIGTERM)
    ui.ui.messageBox('Salvo:\n%s\n%s' % paths, 'IgorSave')

def on_closing(args):
    """Auto mode. Never pops a dialog here (Fusion may be quitting): failures go to a log next to the config."""
    try:
        cfg = load_cfg()
        doc = args.document
        if cfg.get('auto') and doc.products.itemByProductType('DesignProductType'):
            export(doc, cfg['folder'])
    except Exception:
        import traceback, time
        with open(CFG.replace('.json', '.log'), 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + traceback.format_exc() + '\n')
