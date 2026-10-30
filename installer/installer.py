"""IgorSurface installer: copies the bundled add-in into Fusion's AddIns folder. Build: see installer/build.bat."""
import os, shutil, sys, webbrowser
import tkinter as tk
from tkinter import messagebox

VERSION = '1.2.0'
INSTAGRAM = 'https://www.instagram.com/igor3dprint/'
COURSE = 'https://hotmart.com/pt-br/club/igor3dprint'
GITHUB = 'https://github.com/igor3dprint-bit/IgorSurface'
BLUE, ORANGE, BG = '#2F8FD8', '#F39C12', '#1E2430'

def src():
    base = getattr(sys, '_MEIPASS', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    return os.path.join(base, 'IgorSurface')

def dst():
    if sys.platform == 'darwin':
        root = os.path.expanduser('~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns')
    else:
        root = os.path.join(os.environ['APPDATA'], 'Autodesk', 'Autodesk Fusion 360', 'API', 'AddIns')
    return os.path.join(root, 'IgorSurface')

def install():
    target = dst()
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(src(), target, ignore=shutil.ignore_patterns('__pycache__'))
    except OSError as e:
        messagebox.showerror('IgorSurface', 'Não consegui copiar (feche o Fusion e tente de novo):\n%s' % e)
        return
    messagebox.showinfo('IgorSurface', 'Instalado em:\n%s\n\nNo Fusion: Utilities > Add-Ins > aba Add-Ins > '
                        'IgorSurface > Run (marque "Run on Startup").' % target)

def main():
    w = tk.Tk()
    w.title('IgorSurface %s' % VERSION)
    w.configure(bg=BG, padx=28, pady=22)
    w.resizable(False, False)
    tk.Label(w, text='IgorSurface', fg='white', bg=BG, font=('Segoe UI', 22, 'bold')).pack()
    tk.Label(w, text='Scan / STL → CAD editável no Fusion', fg='#C8D0DC', bg=BG, font=('Segoe UI', 11)).pack(pady=(0, 16))
    btn = lambda text, color, cmd: tk.Button(w, text=text, command=cmd, bg=color, fg='white', activebackground=color,
                                             relief='flat', font=('Segoe UI', 11, 'bold'), width=30, pady=7, cursor='hand2')
    btn('Instalar no Fusion', BLUE, install).pack(pady=4)
    btn('Curso de modelagem e impressão 3D', ORANGE, lambda: webbrowser.open(COURSE)).pack(pady=4)
    btn('Instagram @igor3dprint', '#C13584', lambda: webbrowser.open(INSTAGRAM)).pack(pady=4)
    link = tk.Label(w, text='Código, ajuda e atualizações no GitHub', fg=BLUE, bg=BG, cursor='hand2', font=('Segoe UI', 9, 'underline'))
    link.pack(pady=(14, 0)); link.bind('<Button-1>', lambda e: webbrowser.open(GITHUB))
    tk.Label(w, text='Grátis e open source. Usou em vídeo? Cite @igor3dprint na descrição.', fg='#8A94A6', bg=BG,
             font=('Segoe UI', 8)).pack(pady=(6, 0))
    w.mainloop()

if __name__ == '__main__':
    main()
