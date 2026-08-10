$ErrorActionPreference = "Stop"
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean JavSPWeb.spec
Write-Host "已生成 dist\\JavSP-Web.exe"
