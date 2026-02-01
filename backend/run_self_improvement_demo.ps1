# Run Dashboard and Demo Together
# This starts both the dashboard and the self-improvement demo

Write-Host "Starting WeavelT Self-Improvement System" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Gray
Write-Host ""

# Start dashboard in background
Write-Host "1️⃣  Starting Dashboard Server (port 8001)..." -ForegroundColor Yellow
Start-Job -ScriptBlock {
    Set-Location c:\projects\weaveit\backend
    C:/projects/weaveit/.venv/Scripts/python.exe -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8001
} -Name "Dashboard"

Start-Sleep -Seconds 3

# Open browser
Write-Host "2️⃣  Opening Dashboard in browser..." -ForegroundColor Yellow
Start-Process "http://localhost:8001"

Start-Sleep -Seconds 2

# Run demo
Write-Host "3️⃣  Starting Self-Improvement Demo (100 iterations)..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Watch your browser to see the AI learn in real-time!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Gray
Write-Host ""

Set-Location c:\projects\weaveit\backend
C:/projects/weaveit/.venv/Scripts/python.exe dashboard/demo_self_improvement.py

Write-Host ""
Write-Host "✅ Demo Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Stopping dashboard..." -ForegroundColor Yellow
Stop-Job -Name "Dashboard"
Remove-Job -Name "Dashboard"
Write-Host "Done!" -ForegroundColor Green
