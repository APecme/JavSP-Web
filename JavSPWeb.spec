from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
datas = [(str(root / "javsp_web" / "web"), "javsp_web/web"), (str(root / "vendor" / "JavSP"), "vendor/JavSP")]
datas += collect_data_files("pystray")

a = Analysis(["launcher.py"], pathex=[str(root), str(root / "vendor" / "JavSP")], datas=datas, hiddenimports=[
    "uvicorn", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "pystray", "javsp_web.server", "javsp.__main__",
    "javsp.web.airav", "javsp.web.arzon", "javsp.web.arzon_iv", "javsp.web.avsox", "javsp.web.avwiki",
    "javsp.web.dl_getchu", "javsp.web.fanza", "javsp.web.fc2", "javsp.web.fc2fan", "javsp.web.fc2ppvdb",
    "javsp.web.gyutto", "javsp.web.jav321", "javsp.web.javbus", "javsp.web.javdb", "javsp.web.javlib",
    "javsp.web.javmenu", "javsp.web.mgstage", "javsp.web.njav", "javsp.web.prestige", "javsp.web.proxyfree",
    "javsp.web.translate", "javsp.cropper.slimeface_crop"
])
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="JavSP-Web",
    icon=str(root / "javsp_web" / "web" / "assets" / "javsp-logo.ico"),
    console=False,
    onefile=True,
)
