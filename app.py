import os
import subprocess
from datetime import datetime
from flask import Flask, jsonify, redirect, render_template_string, request, url_for

app = Flask(__name__)

WORKFLOWS = {
    "daily_leads": {
        "name": "Generate Daily Leads",
        "command": ["python", r"C:\Users\ParallelBot\Desktop\BookingApp-Leads-Automator\run_daily.py"],
    },
    "build_outreach": {
        "name": "Build Outreach CSV",
        "command": ["python", r"C:\Users\ParallelBot\Desktop\Cash-Tonight-Pack\build_outreach_csv.py"],
    },
    "premium_send": {
        "name": "Run Premium Auto-Send",
        "command": ["python", r"C:\Users\ParallelBot\Desktop\Cash-Tonight-Pack\auto_send_premium.py"],
    },
    "noshow_os": {
        "name": "Launch No-Show Killer OS",
        "command": ["python", r"C:\Users\ParallelBot\Desktop\NoShowKillerOS\app.py"],
    },
    "free_hub": {
        "name": "Launch Free Outreach Hub",
        "command": ["python", r"C:\Users\ParallelBot\Desktop\Cash-Free-Outreach\app.py"],
    },
}

RUN_LOG = []
MAX_LOG = 200


def add_log(entry):
    RUN_LOG.insert(0, entry)
    if len(RUN_LOG) > MAX_LOG:
        del RUN_LOG[MAX_LOG:]


def run_cmd(key):
    wf = WORKFLOWS[key]
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        p = subprocess.run(wf["command"], capture_output=True, text=True, timeout=180)
        ok = p.returncode == 0
        out = (p.stdout or "")[-4000:]
        err = (p.stderr or "")[-2000:]
        add_log({
            "time": started,
            "workflow": wf["name"],
            "status": "OK" if ok else f"ERR {p.returncode}",
            "output": (out + ("\n" + err if err else "")).strip()
        })
        return ok
    except Exception as e:
        add_log({
            "time": started,
            "workflow": wf["name"],
            "status": "EXCEPTION",
            "output": str(e)
        })
        return False


HTML = """
<!doctype html>
<html>
<head>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>JARVIS Control Center</title>
  <style>
    :root{--bg:#030712;--card:#0b1220;--line:#1f2937;--text:#e5e7eb;--muted:#94a3b8;--cyan:#22d3ee;--green:#22c55e;--amber:#f59e0b;}
    body{margin:0;background:radial-gradient(circle at 20% 0%, #0b1f35 0%, var(--bg) 45%);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}
    .wrap{max-width:1200px;margin:0 auto;padding:20px}
    .hdr{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
    .title{font-size:30px;font-weight:800;letter-spacing:1px}
    .sub{color:var(--muted);font-size:13px}
    .grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px;margin-top:16px}
    .card{background:linear-gradient(180deg,#0b1220,#080d18);border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:0 0 0 1px #0a1424 inset}
    .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
    .v{font-size:24px;font-weight:800;color:var(--cyan);margin-top:6px}
    .section{margin-top:16px}
    .section h3{margin:0 0 10px 0;font-size:16px;color:#cbd5e1}
    .wf{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:10px}
    .btn{width:100%;padding:10px 12px;border:none;border-radius:10px;cursor:pointer;font-weight:700}
    .go{background:linear-gradient(90deg,#22d3ee,#3b82f6);color:#031225}
    .runall{background:linear-gradient(90deg,#22c55e,#14b8a6);color:#052014}
    .log{max-height:380px;overflow:auto}
    .item{border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:8px;background:#060b15}
    .meta{font-size:12px;color:var(--muted);margin-bottom:6px}
    pre{white-space:pre-wrap;font-size:12px;color:#d1d5db;margin:0}
    a{color:#93c5fd}
  </style>
</head>
<body>
<div class='wrap'>
  <div class='hdr'>
    <div>
      <div class='title'>JARVIS CONTROL CENTER</div>
      <div class='sub'>Comprehensive workflow orchestration dashboard</div>
    </div>
    <form method='post' action='/run_all'><button class='btn runall'>Run Core Pipeline</button></form>
  </div>

  <div class='grid'>
    <div class='card'><div class='k'>Workflows</div><div class='v'>{{wf_count}}</div></div>
    <div class='card'><div class='k'>Runs Logged</div><div class='v'>{{log_count}}</div></div>
    <div class='card'><div class='k'>Last Status</div><div class='v' style='color:{{ last_color }}'>{{last_status}}</div></div>
    <div class='card'><div class='k'>System Time</div><div class='v' style='font-size:18px'>{{now}}</div></div>
  </div>

  <div class='section'>
    <h3>Workflow Controls</h3>
    <div class='wf'>
      {% for key,w in workflows.items() %}
      <div class='card'>
        <div style='font-weight:700;margin-bottom:8px'>{{w['name']}}</div>
        <form method='post' action='/run/{{key}}'><button class='btn go'>Execute</button></form>
      </div>
      {% endfor %}
    </div>
  </div>

  <div class='section'>
    <h3>Execution Log</h3>
    <div class='log'>
      {% for l in logs %}
      <div class='item'>
        <div class='meta'>{{l['time']}} • {{l['workflow']}} • {{l['status']}}</div>
        <pre>{{l['output']}}</pre>
      </div>
      {% endfor %}
      {% if not logs %}<div class='card'>No runs yet.</div>{% endif %}
    </div>
  </div>
</div>
</body></html>
"""


@app.get("/")
def home():
    last = RUN_LOG[0]["status"] if RUN_LOG else "IDLE"
    color = "#22c55e" if "OK" in last else ("#f59e0b" if last == "IDLE" else "#ef4444")
    return render_template_string(
        HTML,
        workflows=WORKFLOWS,
        logs=RUN_LOG,
        wf_count=len(WORKFLOWS),
        log_count=len(RUN_LOG),
        last_status=last,
        last_color=color,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@app.post("/run/<key>")
def run_one(key):
    if key in WORKFLOWS:
        run_cmd(key)
    return redirect(url_for("home"))


@app.post("/run_all")
def run_all():
    for key in ["daily_leads", "build_outreach"]:
        run_cmd(key)
    return redirect(url_for("home"))


@app.get("/api/status")
def api_status():
    return jsonify({
        "workflows": list(WORKFLOWS.keys()),
        "log_count": len(RUN_LOG),
        "last": RUN_LOG[0] if RUN_LOG else None,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8910)
