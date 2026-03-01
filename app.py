import os
import sqlite3
import random
from datetime import datetime
from flask import Flask, redirect, render_template_string, request, url_for

app = Flask(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "jarvis.db")

SPECIALISTS = {
    "planner": {"name": "Planner", "emoji": "🧠", "desc": "Breaks goals into actionable plans", "active": True, "score": 100},
    "coder": {"name": "Coder", "emoji": "💻", "desc": "Implements the current plan", "active": True, "score": 100},
    "debugger": {"name": "Debugger", "emoji": "🐞", "desc": "Finds/fixes issues and verifies output", "active": True, "score": 100},
    "reviewer": {"name": "Reviewer", "emoji": "✅", "desc": "Final quality gate + handoff", "active": True, "score": 100},
}

RUN_LOG = []
MAX_LOG = 500


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
            max_steps INTEGER DEFAULT 10,
            confidence INTEGER DEFAULT 50,
            planner_cycles INTEGER DEFAULT 0,
            coder_cycles INTEGER DEFAULT 0,
            debugger_cycles INTEGER DEFAULT 0,
            reviewer_cycles INTEGER DEFAULT 0,
            recode_count INTEGER DEFAULT 0,
            plan_text TEXT DEFAULT '',
            code_text TEXT DEFAULT '',
            debug_text TEXT DEFAULT '',
            review_text TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    con.commit()

    # lightweight migration for older dbs
    cols = {r[1] for r in con.execute("PRAGMA table_info(tasks)").fetchall()}
    migrations = {
        "confidence": "ALTER TABLE tasks ADD COLUMN confidence INTEGER DEFAULT 50",
        "planner_cycles": "ALTER TABLE tasks ADD COLUMN planner_cycles INTEGER DEFAULT 0",
        "coder_cycles": "ALTER TABLE tasks ADD COLUMN coder_cycles INTEGER DEFAULT 0",
        "debugger_cycles": "ALTER TABLE tasks ADD COLUMN debugger_cycles INTEGER DEFAULT 0",
        "reviewer_cycles": "ALTER TABLE tasks ADD COLUMN reviewer_cycles INTEGER DEFAULT 0",
        "recode_count": "ALTER TABLE tasks ADD COLUMN recode_count INTEGER DEFAULT 0",
    }
    for col, sql in migrations.items():
        if col not in cols:
            con.execute(sql)
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
    if not kwargs:
        return
    con = db()
    fields = ", ".join([f"{k}=?" for k in kwargs.keys()])
    values = list(kwargs.values())
    sql = f"UPDATE tasks SET {fields}, updated_at=? WHERE id=?"
    con.execute(sql, values + [now(), task_id])
    con.commit()
    con.close()


def get_task(task_id):
    con = db()
    row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    con.close()
    return row


def specialist_active(name):
    return SPECIALISTS.get(name, {}).get("active", False)


def adjust_score(agent, delta):
    old = SPECIALISTS[agent]["score"]
    SPECIALISTS[agent]["score"] = max(1, min(100, old + delta))


def route_to_planner(task_id, t, reason):
    update_task(
        task_id,
        owner="planner",
        status="in_progress",
        planner_cycles=t["planner_cycles"] + 1,
        confidence=max(1, t["confidence"] - 8),
    )
    adjust_score("planner", -2)
    add_log(f"Task #{task_id}: {reason} -> routed to Planner")


def route_to_coder(task_id, t, reason):
    update_task(
        task_id,
        owner="coder",
        status="in_progress",
        coder_cycles=t["coder_cycles"] + 1,
        confidence=max(1, t["confidence"] - 5),
        recode_count=t["recode_count"] + 1,
    )
    adjust_score("coder", -1)
    add_log(f"Task #{task_id}: {reason} -> routed to Coder")


def step_task(task_id):
    t = get_task(task_id)
    if not t:
        return
    if t["status"] in ("done", "failed"):
        return
    if t["step_count"] >= t["max_steps"]:
        update_task(task_id, status="failed", confidence=max(1, t["confidence"] - 15))
        add_log(f"Task #{task_id} failed (max step limit reached)")
        return

    owner = t["owner"]
    if not specialist_active(owner):
        add_log(f"Task #{task_id} paused: {owner} lane disabled")
        return

    step_count = t["step_count"] + 1

    if owner == "planner":
        plan = (
            f"Plan v{step_count}:\n"
            "1) Define measurable success criteria\n"
            "2) Build smallest shippable increment\n"
            "3) Verify against edge cases and user goals"
        )
        conf = min(99, t["confidence"] + random.randint(6, 12))
        update_task(
            task_id,
            owner="coder",
            status="in_progress",
            step_count=step_count,
            planner_cycles=t["planner_cycles"] + 1,
            plan_text=plan,
            confidence=conf,
        )
        adjust_score("planner", +1)
        add_log(f"Planner -> Coder for Task #{task_id} (confidence {conf}%)")

    elif owner == "coder":
        code = (
            f"Implementation v{step_count}:\n"
            "- Features implemented from plan\n"
            "- Added validation + error handling\n"
            "- Ready for debugger pass"
        )
        conf = min(99, t["confidence"] + random.randint(3, 8))
        update_task(
            task_id,
            owner="debugger",
            status="in_progress",
            step_count=step_count,
            coder_cycles=t["coder_cycles"] + 1,
            code_text=code,
            confidence=conf,
        )
        adjust_score("coder", +1)
        add_log(f"Coder -> Debugger for Task #{task_id} (confidence {conf}%)")

    elif owner == "debugger":
        # Policy: if fails 2+ times, send back to planner; otherwise coder
        should_fail = (t["recode_count"] < 2 and step_count % 2 == 0) or (t["confidence"] < 45)
        if should_fail:
            debug = (
                f"Debug pass v{step_count}:\n"
                "- Blocking defects found\n"
                "- Needs rework before review"
            )
            update_task(
                task_id,
                step_count=step_count,
                debugger_cycles=t["debugger_cycles"] + 1,
                debug_text=debug,
            )
            adjust_score("debugger", -1)

            latest = get_task(task_id)
            if latest["recode_count"] >= 2:
                route_to_planner(task_id, latest, "debug failed 2x")
            else:
                route_to_coder(task_id, latest, "debug found defects")
        else:
            debug = (
                f"Debug pass v{step_count}:\n"
                "- Core checks passed\n"
                "- No blocking issues"
            )
            conf = min(99, t["confidence"] + random.randint(4, 10))
            update_task(
                task_id,
                owner="reviewer",
                status="in_progress",
                step_count=step_count,
                debugger_cycles=t["debugger_cycles"] + 1,
                debug_text=debug,
                confidence=conf,
            )
            adjust_score("debugger", +1)
            add_log(f"Debugger -> Reviewer for Task #{task_id} (confidence {conf}%)")

    elif owner == "reviewer":
        pass_review = t["confidence"] >= 60
        if pass_review:
            review = (
                f"Review v{step_count}:\n"
                "- Output meets success criteria\n"
                "- Approved for delivery"
            )
            conf = min(100, t["confidence"] + random.randint(1, 5))
            update_task(
                task_id,
                status="done",
                owner="reviewer",
                step_count=step_count,
                reviewer_cycles=t["reviewer_cycles"] + 1,
                review_text=review,
                confidence=conf,
            )
            adjust_score("reviewer", +1)
            add_log(f"Task #{task_id} completed ✅ (confidence {conf}%)")
        else:
            review = (
                f"Review v{step_count}:\n"
                "- Confidence too low for handoff\n"
                "- Routing back to planner"
            )
            update_task(
                task_id,
                step_count=step_count,
                reviewer_cycles=t["reviewer_cycles"] + 1,
                review_text=review,
            )
            adjust_score("reviewer", -2)
            latest = get_task(task_id)
            route_to_planner(task_id, latest, "review confidence too low")


def run_pipeline(task_id, steps=10):
    for _ in range(max(1, steps)):
        t = get_task(task_id)
        if not t or t["status"] in ("done", "failed"):
            break
        step_task(task_id)


init_db()

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
    .logs{max-height:260px;overflow:auto;background:#07101d;border:1px solid var(--line);border-radius:10px;padding:8px}
    .pill{display:inline-block;border:1px solid var(--line);padding:2px 8px;border-radius:999px;font-size:11px;margin-right:6px}
    .flow{display:flex;gap:8px;flex-wrap:wrap}
    .node{padding:8px 12px;border-radius:10px;border:1px solid var(--line);background:#0a1628;font-size:12px}
    .arrow{opacity:.7;align-self:center}
    .score{font-size:11px;color:#c6f4ff}
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
      <div class='sub'>Mastermind flow with routing rules + confidence scoring</div>
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
      <h3>Pipeline Graph</h3>
      <div class='flow'>
        <div class='node'>🧠 Planner</div><div class='arrow'>→</div>
        <div class='node'>💻 Coder</div><div class='arrow'>→</div>
        <div class='node'>🐞 Debugger</div><div class='arrow'>→</div>
        <div class='node'>✅ Reviewer</div>
        <div class='node'>Rule: debug fail 2x → Planner</div>
      </div>
    </div>

    <div class='section'>
      <h3>Specialist Agents</h3>
      <div class='agents'>
        {% for key,a in specialists.items() %}
        <div class='agent'>
          <div><b>{{a['emoji']}} {{a['name']}}</b> <span class='pill'>{{'ACTIVE' if a['active'] else 'PAUSED'}}</span></div>
          <div class='small'>{{a['desc']}}</div>
          <div class='score'>Quality score: {{a['score']}}%</div>
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
        <div class='small'>Status: {{t['status']}} | Owner: {{t['owner']}} | Steps: {{t['step_count']}}/{{t['max_steps']}} | Confidence: {{t['confidence']}}%</div>
        <div class='small'>Loops — P:{{t['planner_cycles']}} C:{{t['coder_cycles']}} D:{{t['debugger_cycles']}} R:{{t['reviewer_cycles']}} | Recode: {{t['recode_count']}}</div>
        <div class='small'>{{t['objective']}}</div>
        <div style='margin-top:6px;'>
          <form method='post' action='/step/{{t['id']}}' style='display:inline;'>
            <button class='btn btn-step'>Run 1 Step</button>
          </form>
          <form method='post' action='/autorun/{{t['id']}}' style='display:inline;'>
            <button class='btn btn-run'>One-Tap Full Cycle</button>
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
        run_pipeline(tid, steps=3)
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
    run_pipeline(task_id, steps=12)
    return redirect(url_for("home"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8910)
