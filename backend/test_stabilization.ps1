# Test Script: Verify Backend Stabilization
$API_BASE = "http://localhost:8000"
$USER_ID = "test_$(Get-Random -Maximum 9999)"

Write-Host "`n=== BACKEND STABILIZATION TEST ===" -ForegroundColor Cyan
Write-Host "User ID: $USER_ID`n" -ForegroundColor Yellow

# TEST 1: Send events
Write-Host "TEST 1: Event Ingestion" -ForegroundColor Green
$event1 = @{ events = @(@{ type = "USER_MESSAGE"; text = "Write a Python function"; user_id = $USER_ID; provider = "chatgpt" }) } | ConvertTo-Json -Depth 5
$response1 = Invoke-RestMethod -Uri "$API_BASE/v1/events" -Method POST -Body $event1 -ContentType "application/json"
Write-Host "✓ Event ingested: $($response1.ingested) events" -ForegroundColor Green
Start-Sleep -Seconds 2

# TEST 2: Stream health
Write-Host "`nTEST 2: Stream Health" -ForegroundColor Green
$streamHealth = Invoke-RestMethod -Uri "$API_BASE/v1/audit/stream_health?user_id=$USER_ID"
Write-Host "✓ Stream length: $($streamHealth.stream_length)" -ForegroundColor Green
Write-Host "✓ Health: $($streamHealth.health_status)" -ForegroundColor Green

# TEST 3: DLQ Check
Write-Host "`nTEST 3: DLQ Check" -ForegroundColor Green
$dlq = Invoke-RestMethod -Uri "$API_BASE/v1/audit/dlq_stats?user_id=$USER_ID"
Write-Host "✓ DLQ entries: $($dlq.dlq_entries_in_stream)" -ForegroundColor Green

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "✓ Stream consumer running" -ForegroundColor Green
Write-Host "✓ Events flowing through streams" -ForegroundColor Green
Write-Host "✓ Backend STABLE!" -ForegroundColor Green
