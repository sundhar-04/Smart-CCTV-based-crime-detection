"""Human-in-the-loop SOC Review Console:
Alert validation, cryptographic audit verification, and dynamic reinforcement weight feedback.
"""
import os, json, time, subprocess, uuid, sys
from flask import Flask, send_from_directory, redirect, abort, request, render_template_string, Response
from .evidence import Chain
from .notify import dispatch

def apply_feedback(out, types, confirmed):
    p = f"{out}/weights.json"
    w = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"scale": {}}
    for ty in types:
        scale = w["scale"].get(ty, 1.0)
        new_scale = scale * (1.15 if confirmed else 0.82)
        w["scale"][ty] = round(min(3.5, max(0.2, new_scale)), 3)
    json.dump(w, open(p, "w", encoding="utf-8"), indent=2)

def _load(path):
    if not os.path.exists(path):
        return []
    items = []
    for line in open(path, encoding="utf-8").read().strip().split("\n"):
        if line.strip():
            try:
                items.append(json.loads(line)["payload"])
            except Exception:
                pass
    return items

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SmartCCTV | SOC</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    :root {
      --bg: #09090b; --card: #18181b; --border: #27272a;
      --text: #fafafa; --text-muted: #a1a1aa;
      --primary: #3b82f6; --success: #10b981; --warning: #f59e0b; --danger: #ef4444;
      --radius: 12px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; padding: 2rem; line-height: 1.5; }
    .container { max-width: 1400px; margin: 0 auto; }
    
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
    .badge { padding: 6px 12px; border-radius: 999px; font-size: 13px; font-weight: 600; background: rgba(16,185,129,0.1); color: var(--success); border: 1px solid rgba(16,185,129,0.2); }
    
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; transition: transform 0.2s, box-shadow 0.2s; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); }
    .card .title { color: var(--text-muted); font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
    .card .value { font-size: 32px; font-weight: 700; margin-top: 8px; }
    
    .panel { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; margin-bottom: 2rem; }
    .panel-title { font-size: 15px; font-weight: 600; margin-bottom: 1rem; color: var(--text); }
    
    .upload-form { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
    input[type=file] { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 0.5rem 1rem; color: var(--text-muted); font-size: 14px; }
    .btn { padding: 0.5rem 1rem; border-radius: 8px; font-weight: 600; font-size: 13px; border: none; cursor: pointer; transition: opacity 0.2s; text-decoration: none; display: inline-block; }
    .btn:hover { opacity: 0.8; }
    .btn-primary { background: var(--primary); color: #fff; }
    .btn-success { background: var(--success); color: #fff; }
    .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
    
    .table-wrapper { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; text-align: left; }
    th { background: rgba(255,255,255,0.02); color: var(--text-muted); font-size: 12px; font-weight: 500; text-transform: uppercase; padding: 1rem 1.5rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
    td { padding: 1rem 1.5rem; border-bottom: 1px solid var(--border); font-size: 14px; vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255,255,255,0.02); }
    
    .status { padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    .s-pending { background: rgba(245,158,11,0.1); color: var(--warning); border: 1px solid rgba(245,158,11,0.2); }
    .s-confirmed { background: rgba(16,185,129,0.1); color: var(--success); border: 1px solid rgba(16,185,129,0.2); }
    .s-dismissed { background: rgba(161,161,170,0.1); color: var(--text-muted); border: 1px solid rgba(161,161,170,0.2); }
    
    .score-high { color: var(--danger); font-weight: 700; }
    .score-mid { color: var(--warning); font-weight: 700; }
    .score-low { color: var(--primary); font-weight: 700; }
    
    .thumb { width: 44px; height: 44px; border-radius: 8px; object-fit: cover; background: var(--bg); border: 1px solid var(--border); }
    .mono { font-family: 'JetBrains Mono', monospace; color: var(--text-muted); font-size: 12.5px; }
    .hint { font-size: 12px; color: var(--text-muted); margin-top: 0.5rem; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--primary)"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
        <h1>SmartCCTV SOC</h1>
      </div>
      <div class="badge">Verified Hash Chain ({{ alerts|length }} Records)</div>
    </div>

    <div class="panel">
      <div class="panel-title">Upload Video for Analysis</div>
      <form class="upload-form" action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="video" accept="video/*" required>
        <button type="submit" class="btn btn-primary">Analyze Video</button>
      </form>
      <div class="hint">Supported: MP4, AVI, MOV, MKV. Processed via YOLOv8 & ByteTrack.</div>
    </div>

    {% if error %}
    <div class="panel" style="border-color:var(--danger); background:rgba(239,68,68,0.05);">
      <div style="color:var(--danger); font-weight:600; margin-bottom:4px;">Analysis Error</div>
      <div style="font-size:14px; color:var(--text-muted);">{{ uploaded_file or 'unknown' }} &mdash; {{ error }}</div>
    </div>
    {% endif %}

    {% if summary %}
    <div class="panel" style="border-color:var(--success); background:rgba(16,185,129,0.05);">
      <div style="color:var(--success); font-weight:600; margin-bottom:1rem;">Analysis Complete &mdash; {{ uploaded_file or 'Video' }}</div>
      <div class="grid" style="margin:0;">
        <div class="card"><div class="title">Frames</div><div class="value" style="color:var(--primary)">{{ summary.frames }}</div></div>
        <div class="card"><div class="title">Detector</div><div class="value" style="font-size:24px;">{{ summary.detector|upper }}</div></div>
        <div class="card"><div class="title">Alerts</div><div class="value" style="color:var(--danger)">{{ summary.alerts_raised }}</div></div>
        <div class="card"><div class="title">Speed</div><div class="value" style="color:var(--warning)">{{ summary.avg_detector_ms }}ms</div></div>
      </div>
    </div>
    {% endif %}

    <div class="grid">
      <div class="card"><div class="title">Total Incidents</div><div class="value" style="color:var(--primary)">{{ alerts|length }}</div></div>
      <div class="card"><div class="title">Pending Review</div><div class="value" style="color:var(--warning)">{{ pending_count }}</div></div>
      <div class="card"><div class="title">Confirmed</div><div class="value" style="color:var(--success)">{{ confirmed_count }}</div></div>
      <div class="card"><div class="title">Dismissed</div><div class="value" style="color:var(--text-muted)">{{ dismissed_count }}</div></div>
    </div>

    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Evidence</th>
            <th>Identifier</th>
            <th>Risk</th>
            <th>Behaviors</th>
            <th>Zone</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {% for a in alerts %}
          <tr>
            <td>
              {% if a.best_shot %}
                <a href="/clip/{{ a.best_shot }}" target="_blank"><img class="thumb" src="/clip/{{ a.best_shot }}" alt="Crop"></a>
              {% else %}
                <div class="thumb" style="display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:10px;">N/A</div>
              {% endif %}
            </td>
            <td>
              <div style="font-weight: 600;">{{ a.id }}</div>
              <div class="mono">{{ a.camera }} | {{ a.entity }}</div>
            </td>
            <td>
              <div class="{% if a.score >= 100 %}score-high{% elif a.score >= 50 %}score-mid{% else %}score-low{% endif %}">
                {{ a.score }}
              </div>
            </td>
            <td><div style="font-size: 13px; color: var(--text-muted);">{{ a.reasons|join(', ') }}</div></td>
            <td><div style="font-weight: 500;">{{ a.zone or 'Global' }}</div></td>
            <td>
              {% set st = decisions.get(a.id, a.status) %}
              <span class="status {% if st == 'CONFIRMED' %}s-confirmed{% elif st == 'DISMISSED' %}s-dismissed{% else %}s-pending{% endif %}">
                {{ st }}
              </span>
            </td>
            <td>
              <div style="display:flex; gap:8px;">
                {% if a.clip %}
                  <a class="btn btn-outline" href="/clip/{{ a.clip }}" target="_blank">Watch</a>
                {% endif %}
                {% if a.id not in decisions and a.status == 'PENDING_CONFIRMATION' %}
                  <a class="btn btn-success" href="/decide/{{ a.id }}/confirm">Confirm</a>
                  <a class="btn btn-outline" href="/decide/{{ a.id }}/dismiss">Dismiss</a>
                {% endif %}
              </div>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""

def create_app(out="out"):
    app = Flask(__name__)
    dec = Chain(f"{out}/decisions.chain.jsonl")

    # Ensure upload directory exists
    upload_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    @app.before_request
    def require_auth():
        # Simple HTTP Basic Auth
        auth = request.authorization
        expected_user = os.environ.get('DASHBOARD_USER', 'admin')
        expected_pass = os.environ.get('DASHBOARD_PASS', 'admin123')
        if not auth or auth.username != expected_user or auth.password != expected_pass:
            return Response('Authentication required to access SOC Review Console.', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

    @app.route("/")
    def index():
        alerts = _load(f"{out}/alerts.chain.jsonl")
        decisions_list = _load(f"{out}/decisions.chain.jsonl")
        decisions = {d["id"]: d["decision"] for d in decisions_list}

        pending_count = sum(1 for a in alerts if a["id"] not in decisions and a.get("status") == "PENDING_CONFIRMATION")
        confirmed_count = sum(1 for d in decisions.values() if d == "CONFIRMED")
        dismissed_count = sum(1 for d in decisions.values() if d == "DISMISSED")

        sorted_alerts = sorted(alerts, key=lambda a: -a.get("score", 0))

        # Check for any recent processing result
        result = request.args.get("result")
        error = request.args.get("error")
        uploaded_file = request.args.get("file")
        summary = None
        if result:
            try:
                summary_path = os.path.join(os.path.abspath(out), result, "summary.json")
                if os.path.exists(summary_path):
                    summary = json.load(open(summary_path))
            except Exception:
                summary = None

        return render_template_string(
            DASHBOARD_HTML,
            alerts=sorted_alerts,
            decisions=decisions,
            pending_count=pending_count,
            confirmed_count=confirmed_count,
            dismissed_count=dismissed_count,
            summary=summary,
            upload_dir=upload_dir,
            error=error,
            uploaded_file=uploaded_file
        )

    @app.route("/upload", methods=["POST"])
    def upload():
        if "video" not in request.files:
            abort(400, "No video file part")
        file = request.files["video"]
        if file.filename == "":
            abort(400, "No selected file")
        # Save upload
        orig_name = file.filename
        filename = f"{uuid.uuid4().hex}_{orig_name}"
        saved_path = os.path.join(upload_dir, filename)
        file.save(saved_path)
        # Create dedicated output folder for this run
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        run_out = os.path.join(out, run_id)
        os.makedirs(run_out, exist_ok=True)
        # Run the pipeline synchronously, capturing output
        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cmd = [
            sys.executable, "-m", "smartcctv.run",
            "--config", "smartcctv/config.json",
            "--source", saved_path,
            "--out", run_out,
        ]
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
            # Save stdout/stderr for debugging
            with open(os.path.join(run_out, "pipeline_stdout.txt"), "w") as f:
                f.write(proc.stdout or "")
            with open(os.path.join(run_out, "pipeline_stderr.txt"), "w") as f:
                f.write(proc.stderr or "")
            # Check if summary.json was produced (pipeline may exit non-zero due to PowerShell stderr warnings)
            summary_exists = os.path.exists(os.path.join(run_out, "summary.json"))
            if not summary_exists and proc.returncode != 0:
                return redirect(f"/?result={run_id}&error=pipeline_failed&file={orig_name}")
        except subprocess.TimeoutExpired:
            return redirect(f"/?result={run_id}&error=timeout&file={orig_name}")
        except Exception as e:
            return redirect(f"/?result={run_id}&error={str(e)[:100]}&file={orig_name}")
        # Redirect back to index with result identifier
        return redirect(f"/?result={run_id}&file={orig_name}")

    @app.route("/clip/<f>")
    def clip(f):
        return send_from_directory(f"{os.path.abspath(out)}/clips", f)

    @app.route("/decide/<aid>/<d>")
    def decide(aid, d):
        alerts = _load(f"{out}/alerts.chain.jsonl")
        a = next((x for x in alerts if x["id"] == aid), None)
        if not a or d not in ("confirm", "dismiss"):
            abort(404)
        ch = dispatch(a, out) if d == "confirm" else None
        dec.append({"id": aid, "decision": d.upper(), "channel": ch, "timestamp": time.time()})
        apply_feedback(out, a.get("types", []), d == "confirm")
        return redirect("/")

    return app

if __name__ == "__main__":
    import sys, threading
    out_folder = sys.argv[1] if len(sys.argv) > 1 else "out"
    
    def retention_cleanup(out_dir, days=30):
        while True:
            try:
                clips_dir = os.path.join(out_dir, "clips")
                if os.path.exists(clips_dir):
                    now = time.time()
                    for f in os.listdir(clips_dir):
                        p = os.path.join(clips_dir, f)
                        if os.path.isfile(p) and (now - os.path.getmtime(p)) > days * 86400:
                            os.remove(p)
            except Exception:
                pass
            time.sleep(3600)  # Check hourly
            
    threading.Thread(target=retention_cleanup, args=(out_folder,), daemon=True).start()
    create_app(out_folder).run(port=5000)
