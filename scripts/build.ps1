<#
.SYNOPSIS
    earside 打包腳本 (PyInstaller onedir)

.DESCRIPTION
    1. 檢查 Python 與必要工具環境
    2. 執行單元測試 (capture 相關測試預設跳過)
    3. 執行 PyInstaller onedir 打包並輸出至 dist/earside/
    4. 任何階段失敗即中斷並 exit 1

.PARAMETER Clean
    清理舊的 build/ 與 dist/ 資料夾再打包。

.PARAMETER SkipTests
    跳過單元測試階段直接進行打包。
#>

[CmdletBinding()]
param (
    [switch]$Clean,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

# 定位專案根目錄
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

Write-Host "==> [earside] 專案根目錄: $ProjectRoot"

# 偵測可用的 Python 執行檔 (避免觸發 Microsoft Store 虛設捷徑)
$PythonPath = $null

function Test-PythonExecutable($path) {
    if (-not $path) { return $false }
    try {
        $p = Start-Process -FilePath $path -ArgumentList "--version" -NoNewWindow -Wait -PassThru -ErrorAction Stop
        return ($p.ExitCode -eq 0)
    } catch {
        return $false
    }
}

if (Test-PythonExecutable "python") {
    $PythonPath = "python"
} elseif (Test-PythonExecutable "py") {
    $PythonPath = "py"
} else {
    $UvPython = Join-Path $env:APPDATA "uv\python\cpython-3.12.11-windows-x86_64-none\python.exe"
    if ((Test-Path $UvPython) -and (Test-PythonExecutable $UvPython)) {
        $PythonPath = $UvPython
    }
}

if (-not $PythonPath) {
    Write-Error "找不到可用的 Python 解譯器，請確認 PATH 或虛擬環境已啟用。"
    exit 1
}

Write-Host "==> 使用 Python: $PythonPath"

# 1. 執行單元測試 (除非指定 -SkipTests)
if (-not $SkipTests) {
    Write-Host "==> 執行單元測試 ($PythonPath -m unittest discover -s tests)..."
    & $PythonPath -m unittest discover -s tests
    if ($LASTEXITCODE -ne 0) {
        Write-Error "單元測試失敗 (Exit code: $LASTEXITCODE)，中止打包。"
        exit 1
    }
    Write-Host "==> 單元測試通過。"
} else {
    Write-Host "==> 已略過單元測試 (-SkipTests)。"
}

# 2. 清理舊產物 (若指定 -Clean)
if ($Clean) {
    Write-Host "==> 清理 build/ 與 dist/..."
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
}

# 3. 檢查 PyInstaller 是否可用
$PyInstallerCmd = $null
$PyInstallerArgs = @()

if (Get-Command "pyinstaller" -ErrorAction SilentlyContinue) {
    $PyInstallerCmd = "pyinstaller"
} else {
    try {
        $p = Start-Process -FilePath $PythonPath -ArgumentList @("-m", "PyInstaller", "--version") -NoNewWindow -Wait -PassThru -ErrorAction Stop
        if ($p.ExitCode -eq 0) {
            $PyInstallerCmd = $PythonPath
            $PyInstallerArgs = @("-m", "PyInstaller")
        }
    } catch {
        $PyInstallerCmd = $null
    }
}

if (-not $PyInstallerCmd) {
    Write-Error "找不到 PyInstaller。請在環境中執行: pip install pyinstaller"
    exit 1
}

# 4. 執行 PyInstaller 打包
Write-Host "==> 開始打包: $PyInstallerCmd $PyInstallerArgs --noconfirm earside.spec"
$AllArgs = $PyInstallerArgs + @("--noconfirm")
if ($Clean) {
    $AllArgs += "--clean"
}
$AllArgs += "earside.spec"

& $PyInstallerCmd @AllArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller 打包失敗 (Exit code: $LASTEXITCODE)。"
    exit 1
}

# 5. 驗證產物
$DistExe = Join-Path $ProjectRoot "dist\earside\earside.exe"
if (Test-Path $DistExe) {
    $DistDir = Join-Path $ProjectRoot "dist\earside"
    $SizeMB = [math]::Round(((Get-ChildItem $DistDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB), 2)
    Write-Host "==> 打包成功！"
    Write-Host "    執行檔: $DistExe"
    Write-Host "    dist/earside 總目錄體積: $SizeMB MB"
} else {
    Write-Error "打包流程完成但找不到 $DistExe。"
    exit 1
}
