"""Smoke tests for AgentGroupChat server."""

import subprocess, time, sys, urllib.request, json, os, signal

BASE = "http://localhost:18766"

def start_server():
    env = os.environ.copy()
    env["AGENTCHAT_PORT"] = "18766"
    proc = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(0.3)
        try:
            urllib.request.urlopen(f"{BASE}/api/health", timeout=2)
            return proc
        except Exception:
            pass
    proc.kill()
    raise RuntimeError("Server failed to start")

def fetch(path):
    return json.loads(urllib.request.urlopen(f"{BASE}{path}", timeout=5).read())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=5).read())

def delete(path):
    req = urllib.request.Request(f"{BASE}{path}", method="DELETE")
    return json.loads(urllib.request.urlopen(req, timeout=5).read())

def check(cond, msg="assertion failed"):
    if not cond:
        raise AssertionError(msg)

def main():
    print("Starting test server...")
    proc = start_server()
    try:
        print("\nSmoke tests:")

        check(fetch("/api/health")["status"] == "ok", "health"); print("  PASS  health")
        check(len(fetch("/api/agents")["agents"]) >= 1, "agents"); print("  PASS  agents")
        check(post("/api/groups", {"group_id": "smoke"})["group_id"] == "smoke", "create group"); print("  PASS  create group")
        check(post("/api/send/smoke", {"from_name":"T","role":"human","text":"hi"})["id"] == 1, "send human"); print("  PASS  send human")
        check(post("/api/send/smoke/designer1", {"text":"x"})["from"] != "", "send agent"); print("  PASS  send agent")
        check(len(fetch("/api/messages/smoke")["messages"]) == 2, "get msgs"); print("  PASS  get messages")
        check(len(fetch("/api/messages/smoke?consumer=designer1")["messages"]) >= 1, "consumer filter"); print("  PASS  consumer filter")
        check(len(fetch("/api/groups/smoke/members")["members"]) >= 1, "members"); print("  PASS  members")
        check(urllib.request.urlopen(f"{BASE}/", timeout=5).status == 200, "frontend"); print("  PASS  frontend")
        check(delete("/api/groups/smoke")["deleted"] == "smoke", "delete group"); print("  PASS  delete group")

        print(f"\nAll 10 tests passed.")
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)

if __name__ == "__main__":
    main()
