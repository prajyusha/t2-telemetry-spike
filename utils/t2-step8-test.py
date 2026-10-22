"""One normal T2 launch, at most five cycles; no restart or credential generation."""
import datetime
import hashlib
import json
import pathlib
import subprocess
import time

BASE = pathlib.Path(__file__).resolve().parent.parent
def run(args, check=True):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=25)
    if check and p.returncode:
        raise RuntimeError(p.stdout)
    return p.stdout

def native(*args, check=True):
    return run(["docker", "exec", "native-platform", *args], check)

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

assert not native("pgrep", "-x", "telemetry2_0", check=False).strip()
before = native("sha256sum", "/opt/certs/client.pem", "/opt/certs/client.p12")
setup = r'''
import pathlib, json, shutil
d=pathlib.Path('/opt/.t2reportprofiles')
shutil.copytree(d, '/opt/t2-orig/profiles-before-test')
for p in d.iterdir():
    if p.is_file(): p.unlink()
fixture=json.loads(pathlib.Path('/mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike-profile.json').read_text())['profiles'][0]
assert fixture['hash']=='t2-spike-step7-clean-v1'
v=fixture['value']; v['Hash']=fixture['hash']
(d/'T2Spike').write_text(json.dumps(v))
'''
native("python3", "-c", setup)
print(native("rbuscli", "setvalues", "Device.X_RDK_WebConfig.webcfgSubdocForceReset", "string", "false"), flush=True)
print(native("rbuscli", "getvalues", "Device.X_RDK_WebConfig.webcfgSubdocForceReset"), flush=True)
native("gcc", "-g", "-O0", "-fsanitize=address", "-I/usr/local/include",
       "/mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike-event.c", "-L/usr/local/lib",
       "-Wl,-rpath,/usr/local/lib", "-ltelemetry_msgsender", "-o", "/tmp/t2-step8-event")
source = BASE / "telemetry/source/reportgen/reportgen.c"
lines = source.read_text().splitlines()
start = next(i for i, s in enumerate(lines) if s == "char *prepareHttpUrl(T2HTTP *http)")
end = next(i for i in range(start+2, len(lines)) if lines[i] == "}")
(BASE / "utils/t2-step8-prepareHttpUrl.txt").write_text(
    f"telemetry/source/reportgen/reportgen.c:{start+1}-{end+1}\n" +
    "\n".join(lines[start:end+1]) + "\n")
started = now()
launch = native("sh", "-c", "ulimit -c unlimited; export ASAN_OPTIONS=detect_leaks=0:abort_on_error=1:log_path=/opt/t2-step8-asan; /usr/local/bin/telemetry2_0")
time.sleep(3)
pid = native("pgrep", "-x", "telemetry2_0", check=False).strip()
print("START", started, "PID", pid, "launch", launch, flush=True)
rows = []
crashed = not bool(pid)
window = started
for cycle in range(1, 6):
    if crashed:
        rows.append({"cycle": cycle, "pid_alive": False, "receipt": None,
                     "status": "Not run: stopped after crash"})
        continue
    with (BASE / "utils/t2-spike.log").open("a") as f:
        f.write(f"SPIKE_MATCH step8-cycle-{cycle} {now()}\n")
    event = native("env", "ASAN_OPTIONS=detect_leaks=0", "/tmp/t2-step8-event", check=False)
    print("TRIGGER", cycle, event.strip(), flush=True)
    time.sleep(30)
    live = native("pgrep", "-x", "telemetry2_0", check=False).strip()
    logs = run(["docker", "logs", "--timestamps", "--since", window, "mockxconf"])
    next_window = now()
    receipts = [l for l in logs.splitlines() if "Data received:" in l]
    rows.append({"cycle": cycle, "checked_at": next_window, "pid": live,
                 "pid_alive": live == pid and bool(pid), "receipt": receipts,
                 "event_result": event.strip()})
    print("CYCLE", json.dumps(rows[-1]), flush=True)
    for receipt in receipts:
        body = json.loads(receipt.split("Data received:", 1)[1].strip())
        markers = {k for item in body.get("Report", []) for k in item}
        if {"SPIKE_GREP", "SPIKE_EVENT", "SPIKE_DM"} <= markers:
            (BASE / "utils/received-all-markers.json").write_text(json.dumps(body, indent=2) + "\n")
    window = next_window
    crashed = live != pid or not bool(pid)
if crashed:
    crash = native("python3", "-c", r'''
import pathlib
files=sorted(pathlib.Path('/opt').glob('t2-step8-asan.*'))
for f in files:
    print('ASAN FILE:', f)
    print(f.read_text())
if not files:
    print('No ASan report found; normal process disappeared.')
''')
    (BASE / "utils/t2-debug-build-crash.txt").write_text(crash)
    print(crash, flush=True)
    restoration = native("python3", "-c", r'''
import pathlib, json, shutil, hashlib
root=pathlib.Path('/opt/t2-orig')
m=json.loads((root/'manifest.json').read_text())
for item in m:
    dst=pathlib.Path(item['path'])
    if dst.exists() or dst.is_symlink(): dst.unlink()
    shutil.copy2(root/dst.relative_to('/'), dst, follow_symlinks=False)
for item in m:
    p=pathlib.Path(item['path'])
    assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'], str(p)
print('RESTORED and hash-verified',len(m),'original artifacts')
''')
    native("ldconfig")
    print(restoration, flush=True)
else:
    restoration = "Not needed: debug T2 survived five cycles"
after = native("sha256sum", "/opt/certs/client.pem", "/opt/certs/client.p12")
assert before == after, "Credential hashes changed"
result = {"started": started, "pid": pid, "cycles": rows, "crashed": crashed,
          "restoration": restoration.strip(), "credentials_unchanged": before == after,
          "final_dm": native("rbuscli", "getvalues", "Device.X_RDK_WebConfig.webcfgSubdocForceReset"),
          "containers": run(["docker", "ps", "--format", "{{.Names}} {{.Status}}"])}
(BASE / "utils/t2-step8-results.json").write_text(json.dumps(result, indent=2) + "\n")
print("RESULT", json.dumps(result), flush=True)
