import os
import sqlite3
from datetime import datetime
from flask import Flask, redirect, render_template_string, request, url_for

app = Flask(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "jarvis.db")

SPECIALISTS = {
    "planner": {"name": "Planner", "emoji": "🧠", "desc": "Breaks goals into actionable plans", "active": True},
    "coder": {"name": "Coder", "emoji": "💻", "desc": "Implements the current plan", "active": True},
    "debugger": {"name": "Debugger", "emoji": "🐞", "desc": "Finds/fixes issues and verifies output", "active": True},
    "reviewer": {"name": "Reviewer", "emoji": "✅", "desc": "Final quality gate + handoff", "active": True},
}

RUN_LOG = []
MAX_LOG = 300


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_log(msg):
    RUN_LOG.insert(0, f"[{now()}] {msg}")
    if len(RUN_LOG) > MAX_LOG:
        del RUN_LOG[MAX_LOG:]


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            objective TEXT,
            status TEXT,
            owner TEXT,
            step_count INTEGER DEFAULT 0,
            max_steps INTEGER DEFAULT 8,
            plan_text TEXT DEFAULT '',
            code_text TEXT DEFAULT '',
            debug_text TEXT DEFAULT '',
            review_text TEXT DEFAULT '',
            needs_recode INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    con.commit()
    con.close()


def get_tasks():
    con = db()
    rows = con.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    con.close()
    return rows


def create_task(title, objective):
    con = db()
    con.execute(
        "INSERT INTO tasks (title, objective, status, owner, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (title, objective, "queued", "planner", now(), now()),
    )
    con.commit()
    task_id = con.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    con.close()
    add_log(f"Task #{task_id} created: {title}")
    return task_id


def update_task(task_id, **kwargs):
    con = db()
    fields = ", ".join([f"{k}=?" for k in kwargs.keys()])
    vals = list(kwargs.values())
    vals.append(task_id)
    con.execute(f"UPDATE tasks SET {fields}, updated_at=? WHERE id=?", vals[:-1] + [now(), task_id])
    con.commit()
    con.close()


def get_task(task_id):
    con = db()
    row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    con.close()
    return row


def specialist_active(name):
    return SPECIALISTS.get(name, {}).get("active", False)


def step_task(task_id):
    t = get_task(task_id)
    if not t:
        return
    if t["status"] in ("done", "failed"):
        return
    if t["step_count"] >= t["max_steps"]:
        update_task(task_id, status="failed")
        add_log(f"Task #{task_id} exceeded step limit and was marked failed")
        return

    owner = t["owner"]
    if not specialist_active(owner):
        add_log(f"Task #{task_id} paused: {owner} is disabled")
        return

    step_count = t["step_count"] + 1

    if owner == "planner":
        plan = (
            f"Plan v{step_count}:\n"
            f"1) Define success criteria for '{t['title']}'\n"
            f"2) Build smallest working version\n"
            f"3) Validate outcomes and iterate"
        )
        update_task(task_id, owner="coder", status="in_progress", step_count=step_count, plan_text=plan, needs_recode=0)
        add_log(f"Planner -> Coder for Task #{task_id}")

    elif owner == "coder":
        code = (
            f"Implementation v{step_count}:\n"
            f"- Built features from plan\n"
            f"- Added basic error handling\n"
            f"- Prepared for debugger pass"
        )
        update_task(task_id, owner="debugger", status="in_progress", step_count=step_count, code_text=code)
        add_log(f"Coder -> Debugger for Task #{task_id}")

    elif owner == "debugger":
        # Simple deterministic loop: every second debugger pass requests recode once, then passes
        needs_recode = 1 if (t["needs_recode"] == 0 and step_count % 2 == 0) else 0
        if needs_recode:
            debug = (
                f"Debug pass v{step_count}:\n"
                f"- Found defects in edge-case handling\n"
                f"- Returning to coder for fixes"
            )
            update_task(task_id, owner="coder", status="in_progress", step_count=step_count, debug_text=debug, needs_recode=1)
            add_log(f"Debugger -> Coder (rework) for Task #{task_id}")
        else:
            debug = (
                f"Debug pass v{step_count}:\n"
                f"- Core checks passed\n"
                f"- No blocking issues"
            )
            update_task(task_id, owner="reviewer", status="in_progress", step_count=step_count, debug_text=debug)
            add_log(f"Debugger -> Reviewer for Task #{task_id}")

    elif owner == "reviewer":
        review = (
            f"Review v{step_count}:\n"
            f"- Output meets success criteria\n"
            f"- Ready for delivery"
        )
        update_task(task_id, status="done", owner="reviewer", step_count=step_count, review_text=review)
        add_log(f"Task #{task_id} completed ✅")


def run_pipeline(task_id, steps=6):
    for _ in range(max(1, steps)):
        t = get_task(task_id)
        if not t or t["status"] in ("done", "failed"):
            break
        step_task(task_id)


PAGE = """
<!doctype html>
<html>
<head>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>JARVIS Orchestrator</title>
  <style>
    :root{--bg:#040914;--card:#0c1424;--line:#26344d;--text:#e6edf7;--muted:#9fb0c9;--cyan:#34d6ff;--green:#35d07f;--amber:#f7b955;--red:#ff6b6b}
    body{margin:0;background:radial-gradient(circle at 15% 0%, #102640 0%, var(--bg) 45%);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif}
    .wrap{max-width:1200px;margin:0 auto;padding:14px}
    .top{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}
    .title{font-size:24px;font-weight:800;letter-spacing:.06em}
    .sub{font-size:12px;color:var(--muted)}
    .grid{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:8px;margin-top:10px}
    .card{background:linear-gradient(180deg,#0f1a2f,#0a1120);border:1px solid var(--line);border-radius:14px;padding:10px}
    .k{font-size:11px;color:var(--muted);text-transform:uppercase}
    .v{font-size:20px;font-weight:800;color:var(--cyan)}
    .row{display:grid;grid-template-columns:1fr;gap:10px;margin-top:10px}
    .section{background:linear-gradient(180deg,#0f1a2f,#0a1120);border:1px solid var(--line);border-radius:14px;padding:10px}
    h3{margin:0 0 8px 0;font-size:15px}
    .agents{display:grid;grid-template-columns:repeat(2,minmax(220px,1fr));gap:8px}
    .agent{border:1px solid var(--line);border-radius:10px;padding:10px;background:#09101d}
    .btn{border:none;border-radius:10px;padding:8px 10px;font-weight:700;cursor:pointer}
    .btn-run{background:linear-gradient(90deg,var(--green),#19b39c);color:#072015}
    .btn-step{background:linear-gradient(90deg,var(--cyan),#4f8cff);color:#06172a}
    .btn-off{background:var(--red);color:#210b0b}
    .btn-on{background:var(--amber);color:#2e1d00}
    .form input,.form textarea{width:100%;box-sizing:border-box;margin:4px 0;padding:8px;border-radius:8px;border:1px solid #3a4f74;background:#081221;color:var(--text)}
    .tasks .task{border:1px solid var(--line);border-radius:10px;padding:8px;margin-bottom:8px;background:#09101d}
    .small{font-size:12px;color:var(--muted)}
    .logs{max-height:220px;overflow:auto;background:#07101d;border:1px solid var(--line);border-radius:10px;padding:8px}
    .pill{display:inline-block;border:1px solid var(--line);padding:2px 8px;border-radius:999px;font-size:11px;margin-right:6px}
    @media (max-width:800px){
      .grid{grid-template-columns:repeat(2,minmax(120px,1fr));}
      .agents{grid-template-columns:1fr;}
      .title{font-size:20px}
    }
  </style>
</head>
<body>
<div class='wrap'>
  <div class='top'>
    <div>
      <div class='title'>JARVIS ORCHESTRATOR</div>
      <div class='sub'>Master-control pipeline: Planner ➜ Coder ➜ Debugger ➜ Reviewer (looping decisions)</div>
    </div>
  </div>

  <div class='grid'>
    <div class='card'><div class='k'>Tasks</div><div class='v'>{{task_count}}</div></div>
    <div class='card'><div class='k'>Done</div><div class='v'>{{done_count}}</div></div>
    <div class='card'><div class='k'>In Progress</div><div class='v'>{{in_count}}</div></div>
    <div class='card'><div class='k'>Logs</div><div class='v'>{{log_count}}</div></div>
  </div>

  <div class='row'>
    <div class='section'>
      <h3>Specialist Agents (Mastermind Controlled)</h3>
      <div class='agents'>
        {% for key,a in specialists.items() %}
        <div class='agent'>
          <div><b>{{a['emoji']}} {{a['name']}}</b> <span class='pill'>{{'ACTIVE' if a['active'] else 'PAUSED'}}</span></div>
          <div class='small'>{{a['desc']}}</div>
          <form method='post' action='/toggle/{{key}}' style='margin-top:6px;'>
            <button class='btn {{'btn-on' if a['active'] else 'btn-off'}}'>{{'Pause' if a['active'] else 'Resume'}}</button>
          </form>
        </div>
        {% endfor %}
      </div>
    </div>

    <div class='section'>
      <h3>Create New Workflow Task</h3>
      <form class='form' method='post' action='/new_task'>
        <input name='title' placeholder='Task title (e.g. Build auth API)' required>
        <textarea name='objective' rows='3' placeholder='Objective / desired outcome' required></textarea>
        <button class='btn btn-run'>Create + Start</button>
      </form>
    </div>

    <div class='section tasks'>
      <h3>Task Board</h3>
      {% for t in tasks %}
      <div class='task'>
        <div><b>#{{t['id']}} {{t['title']}}</b></div>
        <div class='small'>Status: {{t['status']}} | Owner: {{t['owner']}} | Steps: {{t['step_count']}}/{{t['max_steps']}}</div>
        <div class='small'>{{t['objective']}}</div>
        <div style='margin-top:6px;'>
          <form method='post' action='/step/{{t['id']}}' style='display:inline;'>
            <button class='btn btn-step'>Run 1 Step</button>
          </form>
          <form method='post' action='/autorun/{{t['id']}}' style='display:inline;'>
            <button class='btn btn-run'>Auto-Run Pipeline</button>
          </form>
        </div>
      </div>
      {% endfor %}
      {% if not tasks %}<div class='small'>No tasks yet.</div>{% endif %}
    </div>

    <div class='section'>
      <h3>Mastermind Logs</h3>
      <div class='logs'>
        {% for line in logs %}<div class='small'>{{line}}</div>{% endfor %}
        {% if not logs %}<div class='small'>No logs yet.</div>{% endif %}
      </div>
    </div>
  </div>
</div>
</body></html>
"""


@app.get("/")
def home():
    tasks = get_tasks()
    task_count = len(tasks)
    done_count = sum(1 for t in tasks if t["status"] == "done")
    in_count = sum(1 for t in tasks if t["status"] not in ("done", "failed"))
    log_count = len(RUN_LOG)
    return render_template_string(
        PAGE,
        tasks=tasks,
        specialists=SPECIALISTS,
        logs=RUN_LOG,
        task_count=task_count,
        done_count=done_count,
        in_count=in_count,
        log_count=log_count,
    )


@app.post("/new_task")
def new_task():
    title = request.form.get("title", "").strip()
    objective = request.form.get("objective", "").strip()
    if title and objective:
        tid = create_task(title, objective)
        run_pipeline(tid, steps=2)
    return redirect(url_for("home"))


@app.post("/toggle/<name>")
def toggle(name):
    if name in SPECIALISTS:
        SPECIALISTS[name]["active"] = not SPECIALISTS[name]["active"]
        add_log(f"{SPECIALISTS[name]['name']} toggled to {'ACTIVE' if SPECIALISTS[name]['active'] else 'PAUSED'}")
    return redirect(url_for("home"))


@app.post("/step/<int:task_id>")
def step(task_id):
    step_task(task_id)
    return redirect(url_for("home"))


@app.post("/autorun/<int:task_id>")
def autorun(task_id):
    run_pipeline(task_id, steps=10)
    return redirect(url_for("home"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8910)
