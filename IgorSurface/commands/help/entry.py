"""Ajuda: opens the offline user guide (resources/help/index.html) in the default browser."""
import os, webbrowser
from ...lib import ui

CMD_ID = 'IgorSurface_help'
LINKS = (('IgorSurface_instagram', 'Instagram @igor3dprint', 'Abre o Instagram @igor3dprint.', 'https://www.instagram.com/igor3dprint/'),
         ('IgorSurface_hotmart', 'Curso (Hotmart)', 'Abre o curso do Igor no Hotmart.', 'https://hotmart.com/pt-br/club/igor3dprint'))
PAGE = os.path.join(ui.RES, 'help', 'index.html')

def start():
    ui.add_command(CMD_ID, 'Ajuda', 'Guia do IgorSurface: o que cada ferramenta faz, passo a passo e o que fazer se der errado.', created)
    for cid, name, tip, url in LINKS:
        ui.add_command(cid, name, tip, lambda a, url=url: ui.on(('command', a.command.execute), lambda e: webbrowser.open(url)))

def stop():
    ui.remove_command(CMD_ID)
    for cid, *_ in LINKS:
        ui.remove_command(cid)

def created(args):
    # no inputs: runs at once
    ui.on(('command', args.command.execute), lambda a: open_page())

def open_page():
    if not os.path.isfile(PAGE):
        ui.ui.messageBox('Guia não encontrado em:\n' + PAGE, 'IgorSurface')
        return
    webbrowser.open('file:///' + PAGE.replace(os.sep, '/'))
