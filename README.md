# Jarvis Control Center

A comprehensive Iron-Man-style dashboard to control assistant workflows from anywhere.

## Run locally
```powershell
cd C:\Users\ParallelBot\Desktop\Jarvis-Control-Center
python app.py
```

Then expose publicly with Cloudflare tunnel:
```powershell
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8910 --no-autoupdate
```
