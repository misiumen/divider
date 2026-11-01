# PyInstaller one-folder build:  pyinstaller --noconfirm --clean arkham_dividers.spec
# Runtime files (layout.toml, fonts/, icons/, data/) are copied next to the exe by build.ps1,
# not bundled, so they stay editable.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hidden = [], [], []
for mod in ("OCP", "cadquery", "vtkmodules", "shapely", "fontTools", "numpy"):
    d, b, h = collect_all(mod)
    datas += d
    binaries += b
    hidden += h

a = Analysis(
    ["gui.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    # numba/llvmlite (nurbs) and trame (cadquery.fig viewer) are lazy imports this app never reaches
    excludes=["matplotlib", "trimesh", "pyrender", "PIL", "IPython", "PyQt5", "PySide6", "scipy", "pandas", "gradio",
              "numba", "llvmlite", "trame", "trame_client", "trame_server", "trame_vuetify", "trame_vtk"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="ArkhamDividers", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ArkhamDividers")
