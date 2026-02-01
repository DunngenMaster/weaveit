# Start Streamlit Dashboard
# Simpler, Python-native alternative to the WebSocket dashboard

Write-Host "🎨 Starting Streamlit Dashboard..." -ForegroundColor Cyan
Write-Host ""
Write-Host "This dashboard shows:" -ForegroundColor Yellow
Write-Host "  - Real-time learning progress" -ForegroundColor White
Write-Host "  - UCB scores and strategy performance" -ForegroundColor White
Write-Host "  - How often AI picks optimal strategies" -ForegroundColor White
Write-Host "  - Win rates for each domain" -ForegroundColor White
Write-Host ""
Write-Host "📊 Dashboard will open in your browser automatically" -ForegroundColor Green
Write-Host ""

Set-Location c:\projects\weaveit\backend

C:/projects/weaveit/.venv/Scripts/streamlit.exe run dashboard/dashboard_streamlit.py
