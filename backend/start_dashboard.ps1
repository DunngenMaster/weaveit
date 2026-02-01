# Start WeavelT Live Dashboard
# Run this to launch the real-time monitoring dashboard

Write-Host "🔴 Starting WeavelT Live Dashboard..." -ForegroundColor Cyan
Write-Host ""

# Navigate to backend directory
Set-Location c:\projects\weaveit\backend

# Start dashboard server
Write-Host "📊 Dashboard will be available at: http://localhost:8001" -ForegroundColor Green
Write-Host "   Open this URL in your browser to see live updates" -ForegroundColor Yellow
Write-Host ""

# Run dashboard
C:/projects/weaveit/.venv/Scripts/python.exe -m uvicorn dashboard.app:app --host 0.0.0.0 --port 8001 --reload
