# 把 opendreamina 命令安装到用户 PATH：在安装目录创建一个调用
# `python cli/opendreamina.py` 的 wrapper（.cmd），不安装任何第三方依赖。
#
# 用法：
#   pwsh cli/install.ps1
#   powershell -ExecutionPolicy Bypass -File cli\install.ps1
#   pwsh cli/install.ps1 -InstallDir "D:\bin"
#
# 与 AGENTS.md 第 5 条安全红线一致：本脚本不执行 pip install / npm install，
# 仅生成一个几行的 .cmd wrapper。
param(
    [string]$InstallDir = "$env:USERPROFILE\bin"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target = Join-Path $ScriptDir "opendreamina.py"

if (-not (Test-Path $Target)) {
    throw "未找到目标脚本: $Target"
}

# 选择 python 解释器：优先 python（含完整路径），回退 py launcher。
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $PyExe = $pythonCmd.Source
} else {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pyLauncher) {
        throw "未找到 python / py，请先安装 Python 3.9+。"
    }
    $PyExe = "py"
}

# 创建安装目录。
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# 写 wrapper（.cmd）。用 ASCII 编码以兼容 cmd.exe；路径含非 ASCII 时给出警告。
$Wrapper = Join-Path $InstallDir "opendreamina.cmd"
$wrapperContent = "@echo off`r`n`"$PyExe`" `"$Target`" %*`r`n"

if ([regex]::Matches($Target, '[^\x00-\x7F]').Count -gt 0) {
    Write-Warning "目标路径含非 ASCII 字符: $Target"
    Write-Warning ".cmd wrapper 可能无法被 cmd.exe 正确解析。建议把仓库放到纯英文路径，或直接用 python `"$Target`" 调用。"
    # 路径含非 ASCII 时改用 UTF-8（无 BOM），配合 wrapper 顶部 chcp 65001。
    $wrapperContent = "@echo off`r`nchcp 65001 >nul`r`n`"$PyExe`" `"$Target`" %*`r`n"
    [System.IO.File]::WriteAllText($Wrapper, $wrapperContent, (New-Object System.Text.UTF8Encoding $false))
} else {
    Set-Content -Path $Wrapper -Value $wrapperContent -Encoding ASCII
}

# 把 InstallDir 加入用户 PATH（仅追加，不删改现有内容）。
$InstallDirNorm = $InstallDir.TrimEnd('\')
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$existing = if ($userPath) { $userPath -split ';' } else { @() }
$existingNorm = $existing | ForEach-Object { $_.TrimEnd('\') } | Where-Object { $_ -ne '' }
if ($existingNorm -notcontains $InstallDirNorm) {
    $newPath = if ($userPath) { "$userPath;$InstallDir" } else { $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "已将 $InstallDir 加入用户 PATH（新开终端生效）"
} else {
    Write-Host "$InstallDir 已在用户 PATH 中"
}

Write-Host "已安装 opendreamina -> $Wrapper"
Write-Host "调用: $PyExe `"$Target`" %*"
Write-Host ""
Write-Host "验证: 新开终端后执行 opendreamina --version"
