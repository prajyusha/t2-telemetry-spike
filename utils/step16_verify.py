"""Step 16 runtime verification; run from fresh-run after Compose recreation."""
import datetime
import json
import pathlib
import subprocess
import time

def run(command, check=True):
    print("$", command, flush=True)
    p = subprocess.run(command, shell=True, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    print(p.stdout, end="", flush=True)
    if check and p.returncode:
        raise RuntimeError(f"exit {p.returncode}: {command}")
    return p.stdout

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

setup = pathlib.Path("SETUP.md").read_text()
for attempt in range(60):
    logs = run("docker logs mockxconf 2>&1 | grep 'Data Lake Mock Server running'", False)
    if "Data Lake Mock Server running" in logs:
        break
    time.sleep(2)
else:
    raise RuntimeError("Collector not ready")
run("docker exec native-platform pgrep -a rtrouted")
run("docker exec native-platform pgrep -a rfc_provider")
run("docker exec native-platform rbuscli getvalues Device.X_RDK_WebConfig.webcfgSubdocForceReset")
# Execute verbatim runbook CA refresh, HTTPS probe and original-artifact backup commands.
start = setup.index("docker exec mockxconf sh -c 'cp /etc/pki/")
end = setup.index("# Install only with T2 stopped", start)
run(setup[start:end])
run("sh utils/apply-t2-patch.sh normal")
for container, cert in [
    ("native-platform", "/opt/certs/client.pem"),
    ("mockxconf", "/etc/xconf/certs/mock-xconf-server-cert.pem"),
]:
    run(f"docker exec {container} openssl x509 -in {cert} -noout -subject -dates")
    run(f"docker exec {container} openssl x509 -in {cert} -noout -checkend 86400", False)
    run(f"docker exec {container} openssl x509 -in {cert} -noout -checkend 0")
start = setup.index("# Launch only if absent")
end = setup.index("sleep 35", start)
run(setup[start:end])
pid = run("docker exec native-platform pgrep -x telemetry2_0").strip()
start_time = now()
print("RATE_START", start_time, "PID", pid, flush=True)
time.sleep(600)
end_time = now()
receipts = run(f"docker logs --timestamps --since {start_time} --until {end_time} mockxconf 2>&1 | grep 'Data received:'", False)
lines = receipts.splitlines()
print("RATE_RESULT", start_time, end_time, len(lines), "/20", flush=True)
if len(lines) < 20:
    run("docker exec native-platform sh -c 'tail -1000 /opt/logs/telemetry2_0.txt.0'", False)
print("ALL_MARKER_RECEIPTS", json.dumps([x for x in lines if all(m in x for m in ["SPIKE_DM", "SPIKE_GREP", "SPIKE_EVENT"])]), flush=True)
run("docker exec native-platform sh -c 'pgrep -a telemetry2_0; sha256sum /opt/certs/client.pem /opt/certs/client.p12; ls -la /opt/.t2cachedmessages'", False)
run("docker inspect --format '{{json .NetworkSettings.Networks}} {{.State.StartedAt}}' mockxconf")
outage_start = now()
net = "docker-device-mgt-service-test_default"
try:
    run(f"docker network disconnect {net} mockxconf")
    time.sleep(65)
    run("docker exec native-platform sh -c 'grep -E \"curl failed|Report Cached\" /opt/logs/telemetry2_0.txt.0 | tail -12; ls -la /opt/.t2cachedmessages'", False)
finally:
    run(f"docker network connect --alias mockxconf --alias mock-xconf {net} mockxconf")
time.sleep(40)
run("docker exec native-platform sh -c 'grep -E \"Trying to send|Report Sent Successfully\" /opt/logs/telemetry2_0.txt.0 | tail -18; ls -la /opt/.t2cachedmessages'")
run(f"docker logs --timestamps --since {outage_start} mockxconf 2>&1 | grep 'Data received:'", False)
run("docker exec native-platform rbuscli setvalues Device.X_RDK_WebConfig.webcfgSubdocForceReset string false")
run("docker exec native-platform rbuscli getvalues Device.X_RDK_WebConfig.webcfgSubdocForceReset")
run("docker exec native-platform sh -c 'pgrep -a telemetry2_0; sha256sum /opt/certs/client.pem /opt/certs/client.p12'")
run("docker inspect --format '{{json .NetworkSettings.Networks}} {{.State.StartedAt}}' mockxconf")
print("STEP16_DONE", now(), "INITIAL_PID", pid, flush=True)

