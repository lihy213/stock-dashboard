<#
.SYNOPSIS
  Stock Dashboard - Windows 任务计划程序一键配置
.DESCRIPTION
  创建交易时段每小时自动运行的定时任务 (周一至周五 9:30-15:00)
  以管理员身份运行此脚本
#>

$ErrorActionPreference = "Stop"

$TaskName = "StockDashboard_AutoUpdate"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ScriptDir "venv\Scripts\python.exe"
$UpdateScript = Join-Path $ScriptDir "update.py"
$LogDir = Join-Path $ScriptDir "logs"

# 创建日志目录
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Stock Dashboard · 定时任务配置" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "项目目录: $ScriptDir"
Write-Host "Python:    $PythonExe"
Write-Host "脚本:      $UpdateScript"
Write-Host "日志:      $LogDir"
Write-Host ""

# 检查 Python 是否存在
if (-not (Test-Path $PythonExe)) {
    Write-Host "[错误] Python venv 未找到: $PythonExe" -ForegroundColor Red
    Write-Host "请先运行: python -m venv venv && venv\Scripts\pip install akshare jinja2 requests" -ForegroundColor Yellow
    exit 1
}

# 删除旧任务 (如果存在)
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[1/3] 删除旧任务..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "  已删除" -ForegroundColor Green
}

# 创建任务操作
Write-Host "[2/3] 创建新任务..." -ForegroundColor Yellow

# 交易时段: 9:30, 10:30, 11:30, 13:00, 14:00, 15:00
# 周一至周五: 使用 Windows 任务计划程序的 weekly trigger
$Action = New-ScheduledTaskAction -Execute $PythonExe `
    -Argument "`"$UpdateScript`"" `
    -WorkingDirectory $ScriptDir

# 每小时触发 (交易时段)
$Trigger1 = New-ScheduledTaskTrigger -Daily -At "09:30"
$Trigger2 = New-ScheduledTaskTrigger -Daily -At "10:30"
$Trigger3 = New-ScheduledTaskTrigger -Daily -At "11:30"
$Trigger4 = New-ScheduledTaskTrigger -Daily -At "13:00"
$Trigger5 = New-ScheduledTaskTrigger -Daily -At "14:00"
$Trigger6 = New-ScheduledTaskTrigger -Daily -At "15:10"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger1, $Trigger2, $Trigger3, $Trigger4, $Trigger5, $Trigger6 `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Stock Dashboard 行情数据自动更新" | Out-Null

Write-Host "  任务已注册" -ForegroundColor Green

# 立即运行一次
Write-Host "[3/3] 立即运行一次验证..." -ForegroundColor Yellow
try {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 3
    $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "  上次运行: $($taskInfo.LastRunTime)" -ForegroundColor Green
    Write-Host "  运行结果: $($taskInfo.LastTaskResult)" -ForegroundColor $(if($taskInfo.LastTaskResult -eq 0){'Green'}else{'Yellow'})
} catch {
    Write-Host "  运行失败: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  配置完成!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "⏰ 定时规则:" -ForegroundColor White
Write-Host "  周一至周五: 9:30 / 10:30 / 11:30 / 13:00 / 14:00 / 15:10"
Write-Host ""
Write-Host "📋 管理命令:" -ForegroundColor White
Write-Host "  查看任务:  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "  手动运行:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  删除任务:  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host "  查看日志:  Get-Content '$LogDir\*.log' -Tail 30"
Write-Host ""
Write-Host "🌐 网站部署后访问: https://lihy213.github.io/stock-dashboard/" -ForegroundColor Cyan
