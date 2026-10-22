"""Run one bounded Step 10 reporting scenario against the installed T2 build."""
import argparse
import datetime
import json
import pathlib
import subprocess
import time

BASE = pathlib.Path(__file__).resolve().parent.parent
DM = "Device.X_RDK_WebConfig.webcfgSubdocForceReset"
ASAN = "log_path=/opt/asan/t2-patched:abort_on_error=1:detect_leaks=0"


def _run(*args, check=True):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=30)
    if check and result.returncode:
        raise RuntimeError(result.stdout)
    return result.stdout.strip()


def _native(*args, check=True):
    return _run("docker", "exec", "native-platform", *args, check=check)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# PUBLIC_INTERFACE
def main():
    """Verify A (5 clean ASan), B (3 empty-list ASan), or demo (3 normal) cycles."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("A", "B", "demo"))
    parser.add_argument("--trace", action="store_true",
                        help="Capture daemon termination with strace")
    args = parser.parse_args()
    scenario = args.scenario
    assert not _native("pgrep", "-x", "telemetry2_0", check=False), "T2 already running"
    baseline = _native("sha256sum", "/opt/certs/client.pem", "/opt/certs/client.p12",
                       "/opt/t2-orig/manifest.json")
    # Hash every backup file, not just the manifest; never add files to the backup.
    backup_before = _native("sh", "-c",
                            "find /opt/t2-orig -type f -exec sha256sum {} + | sort")
    fixture = json.loads((BASE / "utils/t2-spike-profile.json").read_text())["profiles"][0]
    value = fixture["value"]
    value["Hash"] = "t2-step10-" + scenario + "-v1"
    if scenario == "B":
        value["HTTP"]["RequestURIParameter"] = []
    else:
        value["HTTP"].pop("RequestURIParameter", None)
    # Keep the existing sole profile name. Refuse to discard unrelated profiles.
    _native("python3", "-c", """
import pathlib, sys, json
directory = pathlib.Path('/opt/.t2reportprofiles')
assert {p.name for p in directory.iterdir()} <= {'T2Spike'}, 'Unexpected profiles'
value = json.loads(sys.argv[1])
(directory / 'T2Spike').write_text(json.dumps(value))
""", json.dumps(value))
    flags = ["-g", "-fsanitize=address"] if scenario != "demo" else []
    _native("gcc", *flags, "-I/usr/local/include",
            "/mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike-event.c",
            "-L/usr/local/lib", "-Wl,-rpath,/usr/local/lib",
            "-ltelemetry_msgsender", "-o", "/tmp/t2-step10-event")
    started = _now()
    launch = ["docker", "exec", "-d"]
    if scenario != "demo":
        launch += ["-e", "ASAN_OPTIONS=" + ASAN]
    launch += ["native-platform"]
    if args.trace:
        launch += ["strace", "-f", "-o", f"/opt/asan/step10-{scenario}-trace.txt",
                   "-e", "trace=exit_group,kill,tgkill"]
    _run(*launch, "/usr/local/bin/telemetry2_0")
    time.sleep(2)
    pid = _native("pgrep", "-x", "telemetry2_0")
    assert pid.isdigit(), f"Expected one daemon, found {pid!r}"
    result = {"scenario": scenario, "started": started, "pid": pid,
              "profile": value, "traced": args.trace, "cycles": []}
    window = started
    try:
        for cycle in range(1, 6 if scenario == "A" else 4):
            dm = "true" if cycle % 2 else "false"
            setter = _native("rbuscli", "setvalues", DM, "string", dm)
            getter = _native("rbuscli", "getvalues", DM)
            assert "failed" not in (setter + getter).lower(), setter + getter
            with (BASE / "utils/t2-spike.log").open("a") as stream:
                stream.write(f"SPIKE_MATCH step10-{scenario}-{cycle} {_now()}\n")
            event = _native("env", "ASAN_OPTIONS=" + ASAN, "/tmp/t2-step10-event")
            assert "returned 0" in event, event
            deadline = time.monotonic() + 45
            receipt = None
            while time.monotonic() < deadline:
                live = _native("pgrep", "-x", "telemetry2_0", check=False)
                if live != pid:
                    result["cycles"].append({
                        "cycle": cycle, "checked_at": _now(), "pid": live,
                        "receipt": None, "status": "PID changed/disappeared"})
                    raise RuntimeError(f"T2 PID changed/disappeared: {pid} -> {live}")
                logs = _run("docker", "logs", "--timestamps", "--since", window, "mockxconf")
                for line in logs.splitlines():
                    if "Data received:" not in line:
                        continue
                    body = json.loads(line.split("Data received:", 1)[1].strip())
                    markers = {key: val for item in body.get("Report", [])
                               for key, val in item.items()}
                    if (markers.get("SPIKE_DM") == dm
                            and markers.get("SPIKE_EVENT") == "spike-event-ok"
                            and int(markers.get("SPIKE_GREP", "0")) > 0):
                        receipt = {"line": line, "body": body}
                        break
                if receipt:
                    break
                time.sleep(1)
            row = {"cycle": cycle, "checked_at": _now(), "pid": live,
                   "dm_getter": getter, "event": event, "receipt": receipt}
            result["cycles"].append(row)
            print(json.dumps(row), flush=True)
            if receipt is None:
                raise RuntimeError("No matching all-three-markers collector receipt within 45s")
            # Only save a body actually observed in collector logs.
            if scenario == "A" and cycle == 1:
                (BASE / "utils/received-all-markers.json").write_text(
                    json.dumps(receipt["body"], indent=2) + "\n")
            window = _now()
        result["passed"] = True
    except Exception as error:
        result["passed"] = False
        result["error"] = str(error)
        raise
    finally:
        if scenario != "demo" or not result.get("passed"):
            _native("kill", "-TERM", pid, check=False)
            for _ in range(20):
                if not _native("pgrep", "-x", "telemetry2_0", check=False):
                    break
                time.sleep(1)
            if _native("pgrep", "-x", "telemetry2_0", check=False) == pid:
                result["cleanup"] = "TERM timeout; forced stop between scenarios"
                _native("kill", "-KILL", pid)
                time.sleep(1)
        result["credentials_and_manifest_unchanged"] = baseline == _native(
            "sha256sum", "/opt/certs/client.pem", "/opt/certs/client.p12",
            "/opt/t2-orig/manifest.json")
        result["backup_files_unchanged"] = backup_before == _native(
            "sh", "-c", "find /opt/t2-orig -type f -exec sha256sum {} + | sort")
        result["asan_reports"] = _native("sh", "-c",
                                        "find /opt/asan -name 't2-patched.*' -type f")
        result["final_pid"] = _native("pgrep", "-x", "telemetry2_0", check=False)
        (BASE / f"utils/t2-step10-{scenario}-results.json").write_text(
            json.dumps(result, indent=2) + "\n")
        assert result["credentials_and_manifest_unchanged"], "Protected hashes changed"
        assert result["backup_files_unchanged"], "Backup files changed"
        assert not result["asan_reports"], "ASan report detected"


if __name__ == "__main__":
    main()
