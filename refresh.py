"""One-off refresh from the command line: .venv/bin/python refresh.py [--force-senate] [--no-notify]"""
import json, os, sys
os.environ["NO_SCHEDULER"] = "1"
import app
app._startup()
app.refresh(force_senate="--force-senate" in sys.argv, do_notify="--no-notify" not in sys.argv)
print(json.dumps(app.status(), indent=1))
