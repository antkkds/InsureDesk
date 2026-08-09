# Clean and rebuild
$ErrorActionPreference = 'Continue'
# Kill any lingering python/PyInstaller processes
Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*PyInstaller*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
# Remove build cache
if (Test-Path "C:\Users\user\Desktop\InsureDesk\build\pyinstaller") {
    Remove-Item "C:\Users\user\Desktop\InsureDesk\build\pyinstaller" -Recurse -Force
}
Write-Output "Cleaned. Starting build..."
Set-Location "C:\Users\user\Desktop\InsureDesk"
python -m PyInstaller build/pyinstaller.spec --clean 2>&1
Write-Output "Build complete!"
