# WeavelT - Complete System Startup
# Starts Backend + Dashboard + Frontend

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  WeavelT - Starting Complete System" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Kill any existing Python processes
Write-Host "[1/4] Cleaning up existing processes..." -ForegroundColor Yellow
taskkill /F /IM python.exe 2>$null
Start-Sleep -Seconds 2

# Start Backend (Port 8000)
Write-Host "[2/4] Starting Backend Server (Port 8000)..." -ForegroundColor Green
Start-Job -ScriptBlock {
    Set-Location c:\projects\weaveit\backend
    C:/projects/weaveit/.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
} -Name "Backend" | Out-Null

Start-Sleep -Seconds 5

# Start Dashboard (Port 8001)
Write-Host "[3/4] Starting Live Dashboard (Port 8001)..." -ForegroundColor Magenta
Start-Job -ScriptBlock {
    Set-Location c:\projects\weaveit\backend
    C:/projects/weaveit/.venv/Scripts/python.exe -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8001
} -Name "Dashboard" | Out-Null

Start-Sleep -Seconds 3

# Start Frontend (Port 5174)
Write-Host "[4/4] Starting Frontend (Port 5174)..." -ForegroundColor Yellow
Start-Job -ScriptBlock {
    Set-Location c:\projects\weaveit\electron
    npx vite --host 127.0.0.1 --port 5174
} -Name "Frontend" | Out-Null

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  All Systems Running!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Services:" -ForegroundColor White
Write-Host "  - Backend:     http://localhost:8000" -ForegroundColor Cyan
Write-Host "  - Dashboard:   http://localhost:8001" -ForegroundColor Magenta
Write-Host "  - Frontend:    http://localhost:5174" -ForegroundColor Yellow
Write-Host ""
Write-Host "Opening Dashboard in browser..." -ForegroundColor White
Start-Process "http://localhost:8001"

Write-Host ""
Write-Host "Press any key to view job status or Ctrl+C to stop all services..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

Write-Host ""
Write-Host "Job Status:" -ForegroundColor White
Get-Job | Format-Table -AutoSize

Write-Host ""
Write-Host "To stop all services, run:" -ForegroundColor Yellow
Write-Host "  Get-Job | Stop-Job; Get-Job | Remove-Job" -ForegroundColor Cyan
Write-Host ""
Write-Host "To run self-improvement demo:" -ForegroundColor Yellow
Write-Host "  cd c:\projects\weaveit\backend" -ForegroundColor Cyan
Write-Host "  python dashboard/demo_self_improvement.py" -ForegroundColor Cyan
Write-Host ""
