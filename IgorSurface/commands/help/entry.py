"""Ajuda: opens the project page on GitHub (README = user guide)."""
import webbrowser
from ...lib import ui

CMD_ID = 'IgorSurface_help'
LINKS = (('IgorSurface_instagram', 'Instagram @igor3dprint', 'Abre o Instagram @igor3dprint.', 'https://www.instagram.com/igor3dprint/'),
         ('IgorSurface_hotmart', 'Curso (Hotmart)', 'Abre o curso do Igor no Hotmart.', 'https://hotmart.com/pt-br/club/igor3dprint'))
GUIDE = 'https://github.com/igor3dprint-bit/IgorSurface#readme'

def start():
    ui.add_command(CMD_ID, 'Ajuda', 'Abre a página do IgorSurface no GitHub: o que cada ferramenta faz, instalação e novidades.', created)
    for cid, name, tip, url in LINKS:
        ui.add_command(cid, name, tip, lambda a, url=url: ui.on(('command', a.command.execute), lambda e: webbrowser.open(url)))

def stop():
    ui.remove_command(CMD_ID)
    for cid, *_ in LINKS:
        ui.remove_command(cid)

def created(args):
    # no inputs: runs at once
    ui.on(('command', args.command.execute), lambda a: webbrowser.open(GUIDE))
