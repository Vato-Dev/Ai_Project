"""Exercise a built image in mock mode. Requires Docker CLI on the Jenkins agent."""

import json
import subprocess
import sys
import time
from uuid import uuid4

image = sys.argv[1]
name = "ci-smoke-" + uuid4().hex[:12]
try:
    subprocess.run(
        ["docker", "run", "-d", "--name", name, "-e", "LLM_PROVIDER=mock", image], check=True
    )
    for _ in range(30):
        result = subprocess.run(
            [
                "docker",
                "exec",
                name,
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')",
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("API health check failed")
    payload = json.dumps(
        {"subject": "Password request", "text": "Please help me reset my password."}
    )
    code = (
        "import json,urllib.request; r=urllib.request.Request('http://localhost:8000/api/analyze',"
        f"data={payload!r}.encode(),headers={{'Content-Type':'application/json'}}); "
        "d=json.load(urllib.request.urlopen(r)); assert d['requires_review']; print(d['id'])"
    )
    subprocess.run(["docker", "exec", name, "python", "-c", code], check=True)
finally:
    subprocess.run(
        ["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
