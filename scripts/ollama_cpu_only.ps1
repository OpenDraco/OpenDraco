# ollama_restart.ps1

$port = 11434

# --- Find PIDs using netstat ---
$pids = netstat -ano | findstr ":$port" | ForEach-Object {
    ($_ -split "\s+")[-1]
} | Sort-Object -Unique

# --- Kill those processes ---
foreach ($procId in $pids) {
    if ($procId -match "^\d+$") {
        Write-Host "Killing PID $procId on port $port"
        taskkill /PID $procId /F | Out-Null
    }
}

# --- CPU ONLY (change if you want GPU) ---
$env:CUDA_VISIBLE_DEVICES = "0"
$env:OLLAMA_NO_CUDA = "1"

# Start Ollama
Start-Process -NoNewWindow -FilePath "ollama" -ArgumentList "serve"