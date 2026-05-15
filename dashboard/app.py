from flask import Flask, jsonify, render_template
from utils.state import state
from engine.order_manager import order_manager
import config

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/state")
def get_state():
    return jsonify(state.to_dict())

@app.route("/api/control/<cmd>", methods=["POST"])
def control(cmd):
    if cmd == "pause":
        state.paused = True
    elif cmd == "resume":
        state.paused = False
        state.kill_switch = False
    elif cmd == "kill":
        state.kill_switch = True
        state.paused = True
        order_manager.close_all()
    return jsonify({"ok": True, "cmd": cmd})

def run_dashboard():
    app.run(host="0.0.0.0", port=config.DASHBOARD_PORT, debug=False, use_reloader=False)
