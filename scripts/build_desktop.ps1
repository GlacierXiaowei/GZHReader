param(
    [switch]$SkipInstall,
    [switch]$SkipSidecar
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Desktop = Join-Path $RepoRoot "desktop"

$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if ((Test-Path -LiteralPath $CargoBin) -and ($env:PATH -notlike "*$CargoBin*")) {
    $env:PATH = "$CargoBin;$env:PATH"
}
if (-not (Get-Command link.exe -ErrorAction SilentlyContinue)) {
    $VsDevCmd = "D:\tools\VSBuildTools2022\Common7\Tools\VsDevCmd.bat"
    if (-not (Test-Path -LiteralPath $VsDevCmd)) {
        throw "未找到 Visual Studio Build Tools 2022。"
    }
    $EnvironmentLines = & cmd.exe /d /s /c "`"$VsDevCmd`" -arch=x64 -host_arch=x64 >nul && set"
    foreach ($Line in $EnvironmentLines) {
        if ($Line -match '^([^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
    if (-not (Get-Command link.exe -ErrorAction SilentlyContinue)) {
        throw "Visual Studio 环境加载后仍未找到 link.exe。"
    }
}

if (-not $SkipSidecar) {
    & (Join-Path $PSScriptRoot "build_sidecar.ps1")
}

Push-Location $Desktop
try {
    if (-not $SkipInstall) { npm ci }
    if (-not $env:TAURI_SIGNING_PRIVATE_KEY -and -not $env:TAURI_SIGNING_PRIVATE_KEY_PATH) {
        $DefaultKey = Join-Path $env:USERPROFILE ".tauri\gzhreader-updater.key"
        if (Test-Path -LiteralPath $DefaultKey) {
            $PasswordFile = Join-Path $env:USERPROFILE ".tauri\gzhreader-updater.password"
            if (-not (Test-Path -LiteralPath $PasswordFile)) { throw "未找到更新签名密码文件。" }
            $env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content -LiteralPath $DefaultKey -Raw).Trim()
            $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = (Get-Content -LiteralPath $PasswordFile -Raw).Trim()
        } else {
            throw "未找到更新签名私钥。请设置 TAURI_SIGNING_PRIVATE_KEY 或 TAURI_SIGNING_PRIVATE_KEY_PATH。"
        }
    }
    npm run desktop:build
    if ($LASTEXITCODE -ne 0) { throw "Tauri 桌面安装包构建失败。" }
} finally {
    Pop-Location
}
