# T2 Docker setup

This file preserves the original SETUP.md text, with Step 2 moved before the
Step 3/4 recovery narrative so that history reads in step order. Historical
claims remain unchanged and describe their own observation times, not current
runtime state. Use [SETUP.md](SETUP.md) for current ordered commands and
[SAMPLES.md](SAMPLES.md) for field-by-field collector annotations.

## Scope and prerequisites

This guide covers the JSON-profile T2 spike, its HTTPS collector, and the bounded Step 5 XConf investigation below. XConf loading is not working in the observed image. Install Docker Desktop with Docker Compose and have access to the build's GitHub dependencies. Run commands from this workspace unless a different directory is shown.

The saved successful upload and CA-refresh evidence is in [the fresh-image transcript](utils/t2-fresh-image-evidence.txt); see [the spike report](t2-spike-setup.md) for profile and marker details. Fresh-clone end-to-end success has not been revalidated during Step 2.

## Build and start the two services

For a new workspace, clone the container repository:

```sh
GIT_TERMINAL_PROMPT=0 git clone https://github.com/rdkcentral/docker-device-mgt-service-test
cd docker-device-mgt-service-test
GIT_TERMINAL_PROMPT=0 ./build.sh
cd ..
docker compose -f docker-device-mgt-service-test/compose.yaml -f utils/compose.step4-no-crl.yaml up -d --pull never mock-xconf l2-container
docker info
docker compose -f docker-device-mgt-service-test/compose.yaml -f utils/compose.step4-no-crl.yaml ps
```

For the existing Step 10 environment, before launching T2, install the patched
normal build:

```sh
sh utils/apply-t2-patch.sh normal
```

This requires the preserved `/opt/t2-orig/manifest.json` backup and a stopped T2.
It does not create or replace that backup, regenerate credentials, or restart
containers. See [Step 10](#step-10-patched-http-parser) for the source, build modes,
verification commands, and observed limitations. Do not run the earlier
backup-creation script against the existing backup.

For an existing checkout, skip cloning and enter `docker-device-mgt-service-test` before building. The checked-in `compose.yaml` mounts its parent directory at `/mnt/L2_CONTAINER_SHARED_VOLUME` in both containers. The Compose services map to containers `mockxconf` and `native-platform`. Do not start `nmap-container` for this spike.

For clean-restart validation with both images already installed, skip clone/build and run from the workspace root:

```sh
docker compose -f docker-device-mgt-service-test/compose.yaml -f utils/compose.step4-no-crl.yaml down
docker compose -f docker-device-mgt-service-test/compose.yaml -f utils/compose.step4-no-crl.yaml up -d --pull never mock-xconf l2-container
docker info
docker compose -f docker-device-mgt-service-test/compose.yaml -f utils/compose.step4-no-crl.yaml ps
```

This is container recreation, not credential-preserving recovery: `/opt/.t2reportprofiles`, `/opt/.t2cachedmessages`, and native credentials are not persistent Compose volumes. Capture their names/hashes before `down`. New native-container startup performs the initial client credential generation described below; do not invoke additional client regeneration manually. The collector-only override retains mTLS. Historical outage tests and the Step 5 XConf investigation below are reference evidence, not commands to execute during Step 6.

## Certificate readiness and CA refresh

1. Allow initial certificate setup to complete in both containers. The server exports its root and intermediate CAs; native-platform imports them and generates its client credentials. The server imports the exported client CA chain before starting the collector.
2. Inspect startup logs; `Up` alone does not establish collector readiness:

   ```sh
   docker logs --tail 40 mockxconf
   docker logs --tail 40 native-platform
   ```

3. After server CA generation and native client-credential generation, and before launching T2 or testing uploads, run the exact trust-only refresh used successfully in the spike:

   ```sh
   docker exec -e ENABLE_MTLS=false -e ENABLE_CRL_L3=false native-platform /usr/local/bin/certs.sh
   ```

   Require `[certs] System CA trust store updated` and `[certs] Server CA certificates imported`. The flags apply only to this subprocess: they skip client credential regeneration and CRL setup, not mTLS in T2 or the server. Do not disable TLS verification.

   The script waits for `/mnt/L2_CONTAINER_SHARED_VOLUME/shared_certs/server/root_ca.pem` and removes the shared server CA files after import. Run the refresh only when the current server CA export is available; blindly repeating it after consumption can wait indefinitely.

   On a clean start the native entrypoint may already have consumed that export. If startup logs confirm import but the trust-only refresh is needed, re-export the running collector's current public CA files before the refresh (do not generate a new CA):

   ```sh
   docker exec mockxconf sh -c 'cp /etc/pki/Test-RDK-root/certs/Test-RDK-root.pem /mnt/L2_CONTAINER_SHARED_VOLUME/shared_certs/server/root_ca.pem; cp /etc/pki/Test-RDK-root/Test-RDK-server-ICA/certs/Test-RDK-server-ICA.pem /mnt/L2_CONTAINER_SHARED_VOLUME/shared_certs/server/intermediate_ca.pem'
   ```

4. Require the collector log `Data Lake Mock Server running at https://localhost:50051/`, then verify authenticated HTTPS from native-platform:

   ```sh
   docker exec native-platform curl --fail --show-error --connect-timeout 5 --max-time 15 --cert /opt/certs/client.pem --key /opt/certs/client.pem https://mockxconf:50051/dataLakeMockReportProfile
   ```

   This readiness probe is not proof that T2 sent a report. Stop if the collector is waiting for client certificates or HTTPS fails.

## Step 2 recovery result and mock cleanup

On October 15, Docker info succeeded and both requested containers were Up; neither needed restarting. T2 PID 2817 was running. Second-outage replay was **not observed**: the cache held five reports (289 bytes), T2 logged curl error 7 at `10:04:33.020`, and collector logs since `09:40:00Z` contained no receipt/listen lines. The collector remained in `[certs] Waiting for client certificates...`.

The shared `shared_certs/client/ca-chain.pem` was absent. The server certificate script consumes and deletes this file on initial import, but waits for it again on restart before starting the collector. A collector-only restart therefore requires a renewed export of the existing native client's public CA chain. Restoring that handshake and validating trust is required before another bounded replay check; CA refresh alone does not resolve this startup gate. Do not delete cached reports or regenerate client credentials merely to clear the gate.

The mock reset value was restored and verified using:

```sh
docker exec native-platform rbuscli setvalues Device.X_RDK_WebConfig.webcfgSubdocForceReset string false
docker exec native-platform rbuscli getvalues Device.X_RDK_WebConfig.webcfgSubdocForceReset
```

The getter returned type `string`, value `false`. Older cached reports can still contain `true`; they are historical values, not the current mock state.

## Restarting mockxconf

After a collector outage/restart, if logs show `[certs] Waiting for client certificates...`, re-export only the existing native client's public CA chain:

```sh
docker exec native-platform cp /etc/pki/Test-RDK-root/Test-RDK-client-ICA/Test-RDK-client-ICA_chain.pem /mnt/L2_CONTAINER_SHARED_VOLUME/shared_certs/client/ca-chain.pem
```

The producer is `docker-device-mgt-service-test/native-platform/certs.sh:193`; its source is defined at line 156. This command repeats only the public-chain copy, not the whole certificate setup script. Do not regenerate certificates or keys, restart T2, delete cached reports, or disable TLS verification. The collector imports and removes the shared chain, so its disappearance after import is expected.

Watch timestamped `docker logs mockxconf` for `Client CA chain imported to trust store` and then `Data Lake Mock Server running at https://localhost:50051/`. Leave the running T2 process alone and wait for its next upload cycle. Compare `docker exec native-platform ls -la /opt/.t2cachedmessages` before and after; require T2 HTTP 200/cache-replay lines and matching collector `Data received:` lines, not just an empty directory.

Step 3 on October 15 restored the existing public chain verbatim through the shared mount (equivalent to the command above). Import completed at `10:10:17.440088804Z`, but the enabled CRL-L3 startup branch then failed with `X509_check_private_key:key values mismatch`; mockxconf exited with code 1 at `10:10:17.834658971Z`, before listening on 50051. No restart or certificate-generation command was invoked during Step 3; the already-running container continued its configured CRL-L3 generation automatically after the wait ended. Native client PEM/P12 hashes remained unchanged.

Replay was **not observed**: zero collector listen lines, zero receipt lines, and five reports remained cached in the 292-byte `T2Spike` file. T2 remained PID 2817 and logged curl error 6 after the collector exited. No `utils/received-cached-replay-2.json` was created because no replayed body was received. See [Step 3 evidence](utils/t2-step3-replay-evidence.txt). An owner must resolve the CRL-L3 startup mismatch under separately authorized scope before replay can be verified; do not treat the re-export alone as successful recovery.

## Step 4 collector-only CRL-L3 override

Step 4 explicitly authorized disabling CRL-L3 for this spike; CRL testing remains out of scope. Upstream `docker-device-mgt-service-test/compose.yaml:33` sets `ENABLE_CRL_L3=true` for mock-xconf. The collector certificate script gates L3 PKI generation at `mock-xconf/certs.sh:135-136`; `mock-xconf/entrypoint.sh:66-67` gates CRL services. Do not edit these upstream files.

The local [override](utils/compose.step4-no-crl.yaml) sets only mock-xconf's `ENABLE_CRL_L3` to `"false"`. The merged configuration retains `ENABLE_MTLS=true`. Re-export the existing public client CA chain using the command above before starting the collector, then run from the workspace root:

```sh
docker compose -f docker-device-mgt-service-test/compose.yaml -f utils/compose.step4-no-crl.yaml config
docker compose -f docker-device-mgt-service-test/compose.yaml -f utils/compose.step4-no-crl.yaml up -d --no-deps --pull never mock-xconf
docker logs --timestamps mockxconf
```

This recreates only mockxconf, not native-platform. Startup may generate a new collector CA; when its exported server CA files are available, run the trust-only refresh from the certificate-readiness section. Never regenerate native client credentials or restart T2 to recover.

Observed October 15: `2026-10-15T10:28:28.519455628Z Data Lake Mock Server running at https://localhost:50051/`. T2 initially logged curl 60 after collector recreation; the trust-only refresh completed and skipped native certificate operations. At `10:29:33.075`, T2 logged `Report Sent Successfully over HTTP : 200` and `Trying to send  5 cached reports`; five further HTTP 200s followed at `.103`, `.127`, `.149`, `.171`, and `.193`. The collector logged five matching `REPORT_TYPE=CACHED` bodies, including the two historical `SPIKE_DM=true` values. The cache went from five JSON bodies in a 292-byte `T2Spike` file to an empty directory. One actual receipt is saved in [received-cached-replay-2.json](utils/received-cached-replay-2.json).

## Recommended network-outage test

Disconnect the collector from its Docker network rather than stopping or restarting the container. This avoids repeating certificate startup and its consumed public-chain gate. Determine the actual network with `docker inspect mockxconf`; this workspace uses `docker-device-mgt-service-test_default`.

```sh
docker exec native-platform ls -la /opt/.t2cachedmessages
docker network disconnect docker-device-mgt-service-test_default mockxconf
# Wait at least two reporting intervals (the spike profile uses 30 seconds).
sleep 65
docker exec native-platform sh -c 'grep -E "curl failed|Report Cached" /opt/logs/telemetry2_0.txt.0 | tail -12; ls -la /opt/.t2cachedmessages'
docker network connect --alias mockxconf --alias mock-xconf docker-device-mgt-service-test_default mockxconf
# Allow the next upload cycle, then inspect both sides.
sleep 40
docker exec native-platform sh -c 'grep -E "Trying to send|Report Sent Successfully" /opt/logs/telemetry2_0.txt.0 | tail -18; ls -la /opt/.t2cachedmessages'
docker logs --timestamps --since 3m mockxconf
```

Always reconnect after the observation window, including if an intermediate diagnostic fails. Preserve the `mockxconf` DNS alias used by the profile URL. Require curl errors and cache growth during disconnection, then T2 HTTP 200/cache-replay lines, matching collector cached-body receipts, and an empty cache after reconnection. Compare the collector's `StartedAt`, T2 PID, and native credential hashes before and after; neither service needs restarting for this test.

Observed Step 4: disconnected at `10:31:45Z`; T2 logged curl 6 (`Couldn't resolve host name`) at `10:32:03.031` and `10:32:33.029`. The cache grew from zero to two bodies in a 117-byte `T2Spike` file. Reconnected at `10:32:51Z` with both aliases. At `10:33:03.076`, T2 sent the current report with HTTP 200 and logged `Trying to send  2 cached reports`; cached POSTs succeeded at `.104` and `.129`, with two matching collector `CACHED` receipts. At `10:33:13Z` the cache directory was empty. Collector `StartedAt` remained `2026-10-15T10:28:27.975377336Z`; T2 remained PID 2817 and both native PEM/P12 SHA-256 hashes were unchanged. See [Step 4 evidence](utils/t2-step4-replay-evidence.txt).

## T2 JSON spike

The native entrypoint does not launch T2. Check before starting a duplicate:

```sh
docker exec native-platform pgrep -a telemetry2_0
```

If absent, launch it detached:

```sh
docker exec -d native-platform sh -c "trap '' PIPE; exec /usr/local/bin/telemetry2_0"
```

With this workspace's `utils/t2-spike-profile.json` present, load the JSON profile:

```sh
docker exec native-platform sh -c 'rbuscli setvalues Device.X_RDKCENTRAL-COM_T2.ReportProfiles string "$(cat /mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike-profile.json)"'
```

Allow asynchronous activation and a reporting interval. The destination is `https://mockxconf:50051/dataLakeMockReportProfile`, defined by `utils/t2-spike-profile.json:40`. The collector route is implemented in `docker-device-mgt-service-test/mock-xconf/data-lake-mock.js:102`, with receipt logging at line 108 and port 50051 at line 36. Bare `/dataLakeMock` is not the implemented route.

Check `/opt/logs/telemetry2_0.txt.0`, `/opt/.t2cachedmessages/`, and timestamped collector logs. Successful replay requires collector receipt lines for cached bodies as well as T2 success messages; an empty cache alone is insufficient.

For Step 6, after profile activation append a fresh `SPIKE_MATCH` line to `utils/t2-spike.log`, then trigger the other two markers:

```sh
docker exec native-platform rbuscli setvalues Device.X_RDK_WebConfig.webcfgSubdocForceReset string true
docker exec native-platform rbuscli getvalues Device.X_RDK_WebConfig.webcfgSubdocForceReset
docker exec native-platform gcc -I/usr/local/include /mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike-event.c -L/usr/local/lib -Wl,-rpath,/usr/local/lib -ltelemetry_msgsender -o /tmp/t2-spike-event
docker exec native-platform /tmp/t2-spike-event
docker exec native-platform pgrep -a telemetry2_0
docker logs --timestamps --since 3m mockxconf
```

Require one collector `Data received:` body containing `SPIKE_GREP`, `SPIKE_DM`, and `SPIKE_EVENT` together; save that actual JSON body as `utils/received-all-markers.json`. A local `cJSON Report` line is not delivery evidence. Record the T2 PID at that receipt, wait two further 30-second reporting cycles, and require two further collector receipts with the same T2 PID still alive.

If T2 disappears at any point, do not continue delivery checks or loop restarts. Run the same installed daemon once under GDB with its persisted profile:

```sh
docker exec native-platform gdb -q -batch -ex 'set pagination off' -ex 'set follow-fork-mode child' -ex 'catch vfork' -ex run -ex 'set follow-fork-mode parent' -ex 'delete breakpoints' -ex continue -ex 'thread apply all bt full' --args /usr/local/bin/telemetry2_0
```

This image daemonizes with an initial fork and later uses vfork for helper commands. The catchpoint switches follow mode back to the daemon before those helpers run.

Capture the signal and backtrace, then stop Step 6. Do not fabricate a collector-receipt file from the locally generated report.

## Step 5 bounded XConf investigation

### Missing tr69hostif

Verified October 15: neither `/usr/local/bin/tr69hostif` nor `/usr/bin/tr69hostif` exists. A container-wide name search found only `/opt/logs/tr69hostIf.log.0`; `/etc/mgrlist.conf` does exist. Startup logged:

```text
/usr/local/bin/entrypoint.sh: line 53: /usr/local/bin/tr69hostif: No such file or directory
```

`docker-device-mgt-service-test/native-platform/entrypoint.sh:52-53` starts the WebConfig mock provider and then `/usr/local/bin/tr69hostif -c /etc/mgrlist.conf -p 10999 -s 11999`. The former registers only `Device.X_RDK_WebConfig.webcfgSubdocForceReset` (`native-platform/mock-rfc-providers/rfc_provider.c:36,90-103`); it cannot replace the missing DeviceInfo provider.

The build **does attempt** to produce/install tr69hostif: `native-platform/Dockerfile:131-133` runs `COPY tr69hostif /opt/tr69hostif`, `sh cov_build.sh`, then removes its source tree. Image history confirms those instructions ran. `docker-device-mgt-service-test/build.sh:41,43,49` clones the upstream source, builds the image, then removes the host checkout. Thus absence of a local source folder is expected, but absence of the installed binary is not.

The current upstream [cov_build.sh](https://github.com/rdkcentral/tr69hostif/blob/main/cov_build.sh), read during this investigation, configures at lines 121-122 and runs `make ... install` at 124-126. It lacks `set -e` and ends with unrelated mock-parodus/link/RBUS commands at 128-132. An earlier build/install failure being masked is a hypothesis, not a verified historical cause: the image's exact tr69hostif revision and original failing build output were not recovered. No rebuild was attempted within this timebox.

### URL, prerequisites, and fetch timing

Source paths in this subsection are relative to `telemetry/`.

| Concern | Verified implementation |
| --- | --- |
| URL | `source/xconf-client/xconfclient.h:40` defines `TR181_CONFIG_URL` as `Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.Telemetry.ConfigURL`. `getRemoteConfigURL`, `xconfclient.c:836-916`, calls `getParameterValue(TR181_CONFIG_URL, &paramVal)` at 864 and enforces `https://` at 868. There is no direct URL properties-file fallback in this function. |
| Bus lookup | `source/ccspinterface/busInterface.c:71-94` dispatches `getParameterValue` to RBUS when active; `rbusInterface.c:179-202` calls `rbus_get` and returns failure for a missing entry. |
| MAC | `appendRequestParams`, `xconfclient.c:386-399`, requires WAN MAC for `estbMacAddress`; lines 511-524 require CM MAC for `ecmMacAddress`. In the default/STB branch both map to `Device.DeviceInfo.X_COMCAST-COM_STB_MAC` (`xconfclient.h:81-93`). RDKB/RDKC branches use different macros (`:43-76`). |
| Firmware/model | `xconfclient.c:401-430` requires firmware and ModelName. Model is `Device.DeviceInfo.ModelName`; STB firmware is `Device.DeviceInfo.X_COMCAST-COM_FirmwareFilename`, or the `X_RDKCENTRAL-COM_FirmwareFilename` variant under `RDKV_FW_FLAG` (`xconfclient.h:28,81-85`). |
| Partner/account | `xconfclient.c:447-509` requires Syndication.PartnerId and `Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.AccountInfo.AccountID`; WhoAmI instead requires Bootstrap.OsClass and Bootstrap.PartnerName. Exact names are in `xconfclient.h:34-38`. `source/utils/t2common.c:325-343` enables WhoAmI only when `/etc/device.properties` has `WHOAMI_SUPPORT=true`; the observed properties lack that setting. |
| Other prerequisites | `xconfclient.c:430-445` conditionally requires Manufacturer. Lines 526-567 read `BUILD_TYPE` from `/etc/device.properties`, append fixed controller/channel/VOD values, require timezone on the non-RDKB/non-RDKC path, and append `version=2`. `getTimezone`, lines 219-360, tries output JSON then `/opt/persistent/timeZoneDST`. Privacy data is conditional at 570-579. |
| Before HTTP | `fetchRemoteConfiguration`, `xconfclient.c:779-834`, calls `appendRequestParams` before `doHttpGet`; missing required values prevent the GET. |
| Timing | `initXConfClient`, `xconfclient.c:1447-1467`, starts the worker at initialization. URL retrieval failure retries every 60 seconds (`:1166-1168`); fetch failures retry every 180 seconds, at most five attempts (`:1274-1289`). After completion it waits for a restart event (`:1337-1346`), not an unconditional periodic successful-fetch poll. Compile-time NTP gating can delay the initial fetch (`:1136-1142`). |
| Reload | The checkout's `source/telemetry2_0.c:181-184,272-299` treats signal 12/SIGUSR2 as reload and calls `stopXConfClient`/`startXConfClient`. This did not preserve the process in the observed runtime; see below. |

For example, the decisive source checks are `if (T2ERROR_SUCCESS == getParameterValue(TR181_CONFIG_URL, &paramVal))` (`xconfclient.c:864`) and `if(T2ERROR_SUCCESS == appendRequestParams(requestURL))` (`:806`). Putting `MODEL_NUM` or `DEVICE_MAC` into a properties file does not itself register an RBUS value.

### What upstream functional tests do

`telemetry/test/functional-tests/tests/test_bootup_sequence.py:46-58` disables request caching, kills T2, sets the HTTPS ConfigURL through RBUS, clears persisted XConf/boot flags, enables request caching, starts T2, and waits 65 seconds. Lines 77-85 expect MAC `AA:BB:CC:DD:EE:FF`, firmware `Platform_Cotainer_1.0.0`, model `DOCKER`, partner `global`, and account `Platform_Container_Test_DEVICE`. These tests assume the native DeviceInfo provider is already available; they do not provide a replacement.

`test_xconf_communications.py:93-100` changes ConfigURL, calls `kill_telemetry(12)`, waits, and checks persistence/profile logs. `helper_functions.py:81-86,132-137` implements these helpers as shell `kill` and `rbuscli setvalues`; it does not register missing entries. Its HTTPS helpers use existing client certificates and the system CA bundle (`:30-69,115-129`). `telemetry/test/run_l2.sh:29-61` adds log/persistence paths, compiles a separate table-only mock provider, and invokes pytest suites. The table provider is not a DeviceInfo mock. The destructive full suites were not run.

### Lowest-effort loading attempt and runtime evidence

At `10:56:12Z`, the upstream URL-setting path was attempted:

```sh
docker exec native-platform rbuscli setvalues Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.Telemetry.ConfigURL string https://mockxconf:50050/loguploader/getT2DCMSettings
```

It returned `setvalues failed with return value: 5` / `Entry not found error`; reading ConfigURL also returned error 5. No URL was installed.

The endpoint requires legacy JSON: `processConfigurationXConf`, `telemetry/source/t2parser/t2parserxconf.c:220-255`, reads `urn:settings:TelemetryProfile`, `telemetryProfile:name`, `uploadRepository:URL`, `schedule`, and a marker array. It is not the JSON ReportProfiles wrapper. The staged [T2SpikeXconf response](utils/t2-spike-xconf-response.json) translates the three spike markers and adds explicit model/MAC fields. Its `*/1` schedule is 60 seconds rather than the JSON spike's 30 seconds (`getScheduleInSeconds`, same source, lines 48-80).

The response was deployed without changing upstream source or restarting either container:

```sh
docker cp utils/t2-spike-xconf-response.json mockxconf:/etc/xconf/xconf-dcm-response.json
docker exec native-platform curl --fail --silent --show-error --connect-timeout 5 --max-time 15 --cert /opt/certs/client.pem --key /opt/certs/client.pem https://mockxconf:50050/loguploader/getT2DCMSettings
```

The verified-mTLS curl succeeded and returned `telemetryProfile:name=T2SpikeXconf`. Collector-side logs show the manual GET at `2026-10-15T10:56:56.529236334Z`. This is **not a T2 fetch**. `mock-xconf/getT2DCMSettings.js:42-64,119-121` reads that response file per request; no server restart is necessary.

One upstream-style `docker exec native-platform sh -c 'kill -12 2817'` was then attempted. PID 2817 disappeared without a reload/shutdown log. The same installed daemon was relaunched detached at `10:57:48Z` to attempt recovery with its persisted profile, not with new credentials. Evidence:

```text
20261015 10:56:23.007 ERROR LOG.RDK.T2- Failed to fetch value for parameter Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.Telemetry.ConfigURL
20261015 10:56:23.007 INFO  LOG.RDK.T2- Waiting for 60 sec before trying getRemoteConfigURL
20261015 10:57:48.620 INFO  LOG.RDK.T2- Successfully enabled profile : T2Spike
20261015 10:57:48.623 ERROR LOG.RDK.T2- Failed to fetch value for parameter Device.DeviceInfo.X_RDKCENTRAL-COM_RFC.Feature.Telemetry.ConfigURL
20261015 10:58:18.152 INFO  LOG.RDK.T2- POST url = https://mockxconf:50051/dataLakeMockReportProfile
20261015 10:58:18.152 INFO  LOG.RDK.T2- mTLS defaulted for telemetry
```

The relaunched daemon disappeared during its first upload cycle; the log ends after the mTLS line, with no new HTTP 200 or matching collector receipt. The cause of this process exit is unverified; do not infer it solely from the last log line. At `10:59:28Z`, `pgrep -a telemetry2_0` returned no process. **Final runtime state differs from Step 4: both containers remain Up and network aliases remain intact, but T2 is not running.** No further signals, rebuilds, or restart loops were attempted.

**XConf load result: no.** Zero `T2SpikeXconf` occurrences were found in the T2 log; no enabled-profile line or report from that profile was observed. The `Successfully enabled profile : T2Spike` line above is only the old persisted JSON profile. Its last pre-attempt collector receipt was `2026-10-15T10:56:36.198799547Z Data received: {"Report":[{"SPIKE_DM":"false"}]}`.

### Device identifiers, safety, and stop condition

Post-attempt getters at `10:57:17Z` and again `10:59:28Z`:

```sh
docker exec native-platform rbuscli getvalues Device.DeviceInfo.ModelName
docker exec native-platform rbuscli getvalues Device.DeviceInfo.X_COMCAST-COM_STB_MAC
```

Both returned `Failed to get the data. Error : 5` / `Entry not found error`. Reports have **not** gained device identifiers: the observed old-profile body contains only `SPIKE_DM=false`; there is no XConf report. The legacy parser normally adds `mac`, IP, PartnerId, Version, and AccountId (`t2parserxconf.c:301-315`); explicit MODEL_NAME/DEVICE_MAC markers are staged but have not been activated.

Native `/opt/certs/client.pem` and `/opt/certs/client.p12` SHA-256 hashes matched before and after the attempt. No certificate scripts, native key/certificate writes, TLS-verification bypasses, container recreations, network changes, or cache deletions were performed. WebConfig reset remains the string `false`; the report cache remains empty. The mock response file remains staged in the running collector and is ephemeral across recreation.

**Blocker / owner action:** the native-image owner must supply a working DeviceInfo/ConfigURL RBUS provider (repair tr69hostif build/install, or separately authorize a small mock covering the required parameters). The runtime owner must also investigate why this installed T2 exits on the upstream reload attempt and during the recovery upload, then restore a stable daemon. Original tr69hostif build logs and the exact build revision are needed to prove its installation failure. This bounded Step 5 stops here; profile enablement and an attributed collector report remain unverified.

## Step 6 clean-restart result

October 15: the corrected existing-image Compose restart completed with the collector-only CRL override. Public-CA re-export, trust-only refresh, and authenticated HTTPS succeeded. T2 was manually launched as PID 4053 and accepted the JSON profile. Its first locally generated report contained all three markers, but it disappeared during upload before any matching collector receipt.

The failure did not reproduce under correctly attached GDB; debug PID 4348 sent only DM-marker reports. A separately captured SIGSTOP live stack snapshot is **not** a crash-site backtrace. See [Step 6 evidence](utils/t2-step6-gdb-evidence.txt). No three-marker receipt file was created and normal-run three-cycle PID stability remains unverified. Step 6 stopped without XConf work.

## Step 7 known issue: upload crash and split-profile test

On October 15, Step 7 ran exactly one three-marker GDB reproduction and one normal-run two-profile workaround test. Neither container was recreated, native credentials were not regenerated, and T2 source was not modified.

### Clean profile and reproduced crash

Before the test, T2 was stopped and `/opt/.t2reportprofiles/T2Spike` contained `Hash: t2-spike-v3`, description `Docker three-marker investigation`, and `HTTP.RequestURIParameter: []`. The exact clean replacement is [utils/t2-spike-profile.json](utils/t2-spike-profile.json): profile `T2Spike`, hash `t2-spike-step7-clean-v1`, description `Docker three-marker spike`, 30-second interval, grep/event/DM parameters, and no URI-parameter experiment. The stopped daemon's persisted value was replaced with that fixture's `value` plus its `Hash` before launch.

The clean profile retains HTTP POST to `https://mockxconf:50051/dataLakeMockReportProfile`, compression `None`, JSON `NameValuePair`, root `Report`, and no report timestamp. Its markers are grep count `SPIKE_GREP` searching `SPIKE_MATCH` in the shared `utils/t2-spike.log`; absolute event `SPIKE_EVENT` from component `t2_spike`; and `SPIKE_DM` reading `Device.X_RDK_WebConfig.webcfgSubdocForceReset`. All have `reportEmpty: true`.

The vfork-safe GDB sequence above was used, with `bt full` and `thread apply all bt` after `continue`. Daemon PID 4649 received a fresh grep line, a DM toggle from `true` to `false`, and the event (`t2_event_s returned 0`) by `11:27:52 UTC`, within its first reporting interval. At `11:28:17.162`, it generated:

```json
{"Report":[{"SPIKE_DM":"false"},{"SPIKE_GREP":"1"},{"SPIKE_EVENT":"spike-event-ok"}]}
```

GDB caught **SIGSEGV** in `prepareHttpUrl` from `libreportgen.so.0`, called by `CollectAndReport` from `libbulkdata.so.0`. No matching collector receipt was observed through `11:28:31 UTC`. This establishes the fault site in this run, not the underlying source-level cause.

- [Observed crash backtrace](utils/t2-three-marker-crash-bt.txt): both requested debugger commands executed, but the tool truncated the middle of the all-thread output. The file explicitly preserves only available frames; it is **not a complete all-thread transcript**. GDB and the inferior had exited before this limitation was checked, and no second reproduction was attempted.
- [Generated pre-crash report](utils/t2-three-marker-generated-before-crash.json): actual T2 log body, **not a collector receipt**.

### Two-profile workaround: failed in this test

For the single workaround run, the stopped daemon's old persisted `T2Spike` was replaced by exactly two runtime JSON profiles under `/opt/.t2reportprofiles/`:

| Profile | Hash | Parameters |
| --- | --- | --- |
| T2SpikeLog | `step7-T2SpikeLog-v1` | Original grep and data-model parameters only |
| T2SpikeEvent | `step7-T2SpikeEvent-v1` | Original event parameter only |

Both used description `Step 7 two-profile workaround test`; all other settings were copied unchanged from the clean profile, including the 30-second interval and HTTP configuration without a URI-parameter list. Each persisted object's `Name` matched its filename. These runtime profiles, not the single-profile host fixture, are the workaround inputs.

T2 was started normally, without GDB, as PID 4736. Both profiles logged `Successfully enabled profile` at `11:29:13.634`. The DM value was toggled from `false` to `true`, the sender returned 0, and a fresh `SPIKE_MATCH step7-two-profile-workaround` line was appended before the first reporting deadline. PID 4736 was still alive at `11:29:27 UTC`.

At `11:29:43.151`, T2 generated the event-only body `{"Report":[{"SPIKE_EVENT":"spike-event-ok"}]}` and logged the default and modified upload URL. By `11:29:51 UTC`, PID 4736 was absent. The exit signal/cause was not captured in this normal run; do not assign the GDB fault site to it without evidence. No collector receipt was observed for either split profile, so no receipt files were created. Splitting the profile is **not a validated workaround**, and three-cycle PID stability failed. There was no restart retry or source fix.

The three scheduled PID checks at `11:29:58`, `11:30:28`, and `11:30:58 UTC` all found T2 absent. Collector logs from `11:29:10 UTC` through the completed observation contained zero `Data received:` lines. At `11:31:13 UTC`, both containers remained Up, T2 remained stopped, and the mock DM value was the string `true`. Native client PEM/P12 SHA-256 hashes matched the pre-test values. The two split runtime profiles remain persisted; the host fixture remains the clean single profile. Saved JSON files parsed successfully, and this document retains its final table-based Summary.

## Step 8

October 15: exactly one debug/ASan rebuild and one normal T2 launch were performed. No T2 source edits, native credential regeneration, container recreation, XConf work, or second reproduction occurred.

### Version and URL source findings

Checkout HEAD: `a2f2a545e4bd6170eac96f7c0c46fbd4df6f1654` (`git describe`: `a2f2a54`); `configure.ac` declares telemetry 2.0. The prior fresh-image transcript records the same separately cloned checkout but does not conclusively associate it with the installed artifacts. Native image: `sha256:87ff28ada7cd788f8280834194c2dfd4ad119d2b0b52acc4bd44e5672042352f`.

**Installed commit: unknown.** Daemon strings identify Telemetry 2.0 but no commit identifier was recovered from the daemon or reportgen. Container `build.sh` has no telemetry clone/ref, image history yielded no telemetry build step, and `/opt/WORKDIR` has no retained build checkout. Installed-versus-HEAD equality or mismatch is not established; no `--version` launch was attempted.

| Original artifact | ELF build ID | SHA-256 |
| --- | --- | --- |
| `telemetry2_0` | `d3e459f1ad9406344a041df07d0a2e975387f94d` | `99c874f617027eba949d0e3c218f8dc8492ff1a3d9cd67e0480289d97c1207ca` |
| `libreportgen.so.0.0.0` | `6a0e106a29eab582caa8a190a1d0ab7dc1d42e12` | `45b1e7b184ca3582e71e830ddceb6c293a101a4c90c504207970257f3e2ebecf` |

The [full unedited prepareHttpUrl function](utils/t2-step8-prepareHttpUrl.txt) is from `telemetry/source/reportgen/reportgen.c:1676-1789`. It rejects NULL `http` and failed curl initialization. Line 1692 guards both list pointer and count: `if (http->RequestURIparamList && http->RequestURIparamList->count)`. Original library disassembly also guards the list pointer before reading count; a missing NULL-list guard is not established as the crash explanation.

URL construction does not check `http->URL` or the result of `strdup` at 1689. List elements, `HttpName`, and successful dynamic lookup's `paramValue` are not NULL-checked before use. Parameter realloc failure frees/reset buffers and continues; final URL realloc failure frees buffers and returns NULL. A NULL curl escape result is omitted from length accounting but still passed to `%s` at 1754. These are source observations, not a verified cause of this run's exit.

### Backup and exact build commands

The [exact build script](utils/t2-step8-build.sh) first backed up 46 installed daemon/library artifacts, preserving symlinks, under `/opt/t2-orig/usr/local/`, with SHA-256 manifest `/opt/t2-orig/manifest.json`. It copied our checkout to `/opt/t2-debug-src` excluding `.git` and `.DS_Store`; all generation/build activity occurred in that isolated copy.

Executed from workspace: `docker exec native-platform sh /mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-step8-build.sh`. Its build commands were:

```sh
cd /opt/t2-debug-src
export INSTALL_DIR=/usr/local
export CFLAGS="-g -O0 -fsanitize=address -fno-omit-frame-pointer -I/usr/local/include/rtmessage -I/usr/local/include/msgpack -I/usr/local/include/rbus -I/usr/local/include $(pkg-config --cflags glib-2.0) -DFEATURE_SUPPORT_WEBCONFIG -DRDK_LOGGER -DPERSIST_LOG_MON_REF -DDCMAGENT -DENABLE_MTLS"
export CXXFLAGS="$CFLAGS"
export LDFLAGS="-fsanitize=address -L/usr/local/lib $(pkg-config --libs glib-2.0)"
autoreconf --install
./configure --prefix=/usr/local --enable-rdkcertselector=yes --enable-dynamic-table-support=yes
make -j2 V=1
make install
ldconfig
```

The single rebuild succeeded with ASan; no fallback rebuild or dependency installation was needed. Reportgen had debug sections and daemon `ldd` resolved `libasan.so.6`. Debug daemon build ID: `d3c91c3f962a85a77ee913994bf80747aa37a802`.

### Single test and five-cycle table

Executed `python3 utils/t2-step8-test.py`; the [harness](utils/t2-step8-test.py) contains the exact setup, sender compile, launch, checks, and restoration procedure. Prior profiles were archived under `/opt/t2-orig/profiles-before-test`; split profiles were removed and only clean `T2Spike`, hash `t2-spike-step7-clean-v1`, persisted. DM was set and verified as string `false`.

T2 launched normally without GDB at `11:40:34.990848 UTC`, PID `14654`, with `ulimit -c unlimited` and `ASAN_OPTIONS=detect_leaks=0:abort_on_error=1:log_path=/opt/t2-step8-asan`. The first interval received a fresh grep line and event (`t2_event_s returned 0`) with DM false. At `11:41:04.159`, the local report was `{"Report":[{"SPIKE_DM":"false"},{"SPIKE_GREP":"2"},{"SPIKE_EVENT":"spike-event-ok"}]}`; this is not collector delivery evidence.

| Cycle | PID alive at check | Collector receipt line | Outcome |
| --- | --- | --- | --- |
| 1 | No; 14654 absent at `11:41:10.392586 UTC` | None; zero `Data received:` lines | Disappeared in first interval; stopped |
| 2 | Not checked after stop | Not assessed | Not run |
| 3 | Not checked after stop | Not assessed | Not run |
| 4 | Not checked after stop | Not assessed | Not run |
| 5 | Not checked after stop | Not assessed | Not run |

No all-markers receipt was observed; `utils/received-all-markers.json` was not created. [Actual results](utils/t2-step8-results.json) preserve the run; false PID values in skipped rows are placeholders, not later observations.

### Restoration and diagnostic limitation

No `/opt/t2-step8-asan.*` report or daemon core dump was found in the bounded filesystem inspection. [Saved exit evidence](utils/t2-debug-build-crash.txt) is **not an ASan report or backtrace**. Exit signal and file:line remain unknown; do not assign Step 7's fault site to this run. A separately authorized diagnostic capture is required to meet the file:line requirement; no second run was made.

The original daemon and all 46 backed-up artifacts were restored from `/opt/t2-orig/`, hash-verified against its manifest, and followed by `ldconfig`; daemon/reportgen hashes above matched after restoration. `make install` also installed ancillary `telemetry2_0_client`, which was not in the original backup manifest and is not covered by the restoration claim. The isolated debug build remains for inspection.

Final state: both containers Up, T2 stopped, only clean T2Spike persisted, DM false, native PEM/P12 hashes unchanged. Checkout status remains only pre-existing untracked `.DS_Store`. Step 8 stops with a failed first-cycle delivery test and an unmet file:line capture requirement.

## Step 9 single-run ASan diagnosis

October 15: the retained `/opt/t2-debug-src` build was reinstalled with `make install`, without a fresh rebuild or source edits. `ldd` confirmed `libasan.so.6` in `telemetry2_0`, `libreportgen.so`, and `libbulkdata.so`. Strace was installed in the native container; no native credentials were regenerated. Exactly one T2 launch ran under `strace -f -o /opt/asan/strace.txt -e trace=exit_group,kill,tgkill`, with `ASAN_OPTIONS=log_path=/opt/asan/t2:abort_on_error=1:detect_leaks=0:symbolize=1`.

PID 16279 started at `11:50:38Z` with only clean T2Spike persisted. Fresh grep, event, and DM triggers completed in the first interval. At `11:51:08.168`, its local report contained `SPIKE_DM=false`, `SPIKE_GREP=1`, and `SPIKE_EVENT=spike-event-ok`; no collector receipt was observed. The [actual ASan report](utils/t2-asan-report.txt) identifies a read SEGV in `prepareHttpUrl`, `source/reportgen/reportgen.c:1692`, called by `CollectAndReport`, `source/bulkdata/profile.c:689`. Only four fault-stack frames were emitted; the additional stacks in the report describe thread creation, not fifteen fault frames.

The [exit trace](utils/t2-step9-strace.txt) shows thread 16330 receiving `SIGSEGV`, then `tgkill(16279, 16330, SIGABRT)`, and daemon 16279 killed by `SIGABRT`. Parent/helper `exit_group(0)` lines are not a clean daemon exit. The [diagnostic evidence](utils/t2-step9-evidence.txt) includes the faulting source context and restoration checks.

The evidence-supported initialization defect is in the JSON parser: `processConfiguration`, `source/t2parser/t2parser.c:1861`, uses `malloc(sizeof(T2HTTP))`; `protocolSet` initializes `RequestURIparamList` only when optional `HTTP.RequestURIParameter` exists. Clean T2Spike omits it. The indeterminate non-NULL list pointer reaches `if (http->RequestURIparamList && http->RequestURIparamList->count)` at the fault site. The NULL guard already exists; adding another does not address invalid non-NULL state. The [minimal unapplied diff](utils/t2-prepareHttpUrl-fix.diff) changes this JSON-path allocation to `calloc(1, sizeof(T2HTTP))`. It has not been applied or tested; no second run occurred.

All 46 original artifacts were restored from the unchanged `/opt/t2-orig/`, SHA-256 and symlink-target verified against its manifest, followed by `ldconfig`. Backup artifact hashes were independently rechecked; manifest and native PEM/P12 hashes match their pre-run values. Original daemon/reportgen hashes match the Step 8 table. Both containers remain Up, T2 is stopped, only clean T2Spike is persisted, and DM is string `false`. Strace remains installed and raw `/opt/asan` evidence is retained. The ancillary client remains outside the original backup manifest, as noted in Step 8. Step 9 stops here without applying a source patch.

## Step 10 patched HTTP parser

The repository implementation defect is in JSON `processConfiguration`:
`profile->t2HTTPDest = (T2HTTP *) malloc(sizeof(T2HTTP));` allocates an
uninitialized destination. `protocolSet` calls
`Vector_Create(&(profile->t2HTTPDest->RequestURIparamList))` only inside
`if(jprofileHTTPRequestURIParameter)`. The clean profile omits that property.
`prepareHttpUrl`, called by `CollectAndReport`, reads
`if (http->RequestURIparamList && http->RequestURIparamList->count)`.
The existing NULL guard cannot protect against an indeterminate non-NULL pointer.

The supplied [one-line diff](utils/t2-prepareHttpUrl-fix.diff) changes only this
JSON allocation to `calloc(1, sizeof(T2HTTP))`. It is applied in
`/opt/t2-patched-src`, not the host checkout or `/opt/t2-orig/`.

### Repeatable installation and verification

Run from the workspace root with both existing containers ready and T2 stopped:

```sh
sh utils/apply-t2-patch.sh asan
python3 utils/t2-step10-verify.py A --trace
python3 utils/t2-step10-verify.py B --trace
sh utils/apply-t2-patch.sh normal
python3 utils/t2-step10-verify.py demo
```

The [installer](utils/apply-t2-patch.sh) dispatches into native-platform through
the shared mount. It copies telemetry only if `/opt/t2-patched-src` is absent,
applies the diff or verifies it is already applied, cleans between modes,
builds, installs, runs `ldconfig`, and checks linkage of `telemetry2_0`,
`libreportgen.so`, and `libbulkdata.so`. It refuses to install over a running
daemon or without the original backup. Existing isolated source is reused;
do not assume a later host checkout automatically updates it.

Normal flags follow `telemetry/build_inside_container.sh`: `-Wall -Werror
-Wextra`, the same include/feature defines, and the same cert-selector and
dynamic-table configure options. Architecture-specific GLib paths come from
pkg-config instead of the recipe's hardcoded x86 paths. ASan mode uses `-g -O0
-fsanitize=address -fno-omit-frame-pointer` and sanitizer link flags.
ASan launches retain exactly
`ASAN_OPTIONS=log_path=/opt/asan/t2-patched:abort_on_error=1:detect_leaks=0`.
The three-artifact linkage checks require ASan in sanitizer mode and reject it
in normal mode.

The [verification harness](utils/t2-step10-verify.py) uses clean profile hash
`t2-step10-A-v1`, empty-list hash `t2-step10-B-v1`, and clean demo hash
`t2-step10-demo-v1`. It toggles and reads DM, appends fresh grep input, and
sends the event every cycle. Each cycle requires a collector receipt with the
expected DM value, a positive grep count, and the event value, while checking
the original daemon PID. Results include actual timestamped receipt lines.
The first Run A receipt is saved as
[received-all-markers.json](utils/received-all-markers.json).

ASan runs stop between scenarios; the harness tries TERM for 20 seconds and
records a forced stop if the existing shutdown path stalls. A successful demo
is left running. No cache deletion, native credential regeneration, TLS bypass,
or backup restoration is part of this procedure. Do not rerun the harness
against a running demo without deliberately stopping that process first.

### Other parser allocation findings

The following bounded source audit is separate from the fixed crash path.
No additional parser fixes were made:

| Structure / field | Allocation and conditional initialization | Read / assessment |
| --- | --- | --- |
| JSON `T2RBUS.rbusMethodParamList` | `processConfiguration` uses `malloc(sizeof(T2RBUS))`; `protocolSet` creates the vector only inside `if(jprofileRBUSMethodParamArr)`. | `freeProfile` tests the pointer, and `sendReportsOverRBUSMethod` receives it and calls `Vector_Size`. Missing optional Parameters can leave an invalid pointer. Not the HTTP scenario. |
| `EventMarker.accumulatedTimestamp` | `addParameter` uses `malloc(sizeof(EventMarker))`; in accumulate mode it creates this vector only for `REPORTTIMESTAMP_UNIXEPOCH`. | `source/utils/t2common.c`, `freeEMarker`, evaluates `eMarker->accumulatedTimestamp != NULL` before the timestamp-format condition. Accumulate without timestamps reads unset state. The spike uses absolute events. |
| `JSONEncoding.tsFormat` | JSON `processConfiguration` uses malloc; `encodingSet` assigns `tsFormat` only when optional `jprofileJSONReportTimestamp` exists. | Uninitialized state exists when omitted, but no production read was identified in the bounded search; not claimed as a demonstrated crash. The spike explicitly specifies `None`. |
| JSON `TriggerCondition.type/oprator/reference` | `addTriggerCondition` mallocs without clearing and assigns each string only under its presence check. | `freeTriggerCondition` tests all three pointers. Normal `processConfiguration` first validates these mandatory fields, so omitted-field reachability through that entry point is not established; direct helper use warrants review. |
| MessagePack `T2HTTP` | Also uses malloc. | Unlike JSON, `protocolSetMsgpack` unconditionally creates `RequestURIparamList`; the missing-property defect is not established on that path. |

Evidence is in `telemetry/source/t2parser/t2parser.c` (`processConfiguration`,
`protocolSet`, `addParameter`, `encodingSet`, `addTriggerCondition`,
`protocolSetMsgpack`), `source/bulkdata/profile.c` (`freeProfile`,
`CollectAndReport`), `source/protocol/rbusMethod/rbusmethodinterface.c`
(`sendReportsOverRBUSMethod`), and `source/utils/t2common.c` (`freeEMarker`,
`freeTriggerCondition`).

## Step 11 SIGPIPE-ignore launch

The retained normal installation log, `/tmp/t2-step11-install.log` in
native-platform, records installation from `/opt/t2-patched-src` with normal
compiler flags and a libtool relink of the parser. The installed parser SHA-256
is `ec49885e1a938a33333281326950a501dcaddff6dd745194c1408bba239181ee`,
different from the preserved original
`c05640aff1b65383f5f03d975416a8ad6e9064f61acbc2bf167b74e11f96a510`.
This satisfies the authorized install-log/original-library baseline criterion;
raw build-tree equality is not required after libtool relinking.
Daemon linkage showed no ASan. All 46 original backup entries passed hash and
symlink checks, and credential and manifest hashes matched Step 10.

Source findings: `source/telemetry2_0.c:329-355` has no foreground option and
forks unconditionally. Test 1 is therefore not applicable; no exit code was
captured. `source/protocol/http/multicurlinterface.c:373` sets
`CURLOPT_NOSIGNAL` to `1L`. No SIGPIPE registration was found in the searched
source/include trees; the mention in `sig_handler` at
`source/telemetry2_0.c:153` is not a registration.
The daemon initialization registers other signals before calling
`initTelemetry`, but not SIGPIPE.

On October 16, the ordinary daemon was launched once with the trap wrapper
above, without tracing or debugging, at `06:43:15 UTC`.
Each cycle triggered fresh grep input, the event marker, and the DM value.
All observed collector bodies contained `SPIKE_GREP=1`,
`SPIKE_EVENT=spike-event-ok`, and the expected DM value:

| Cycle | PID at receipt check | Collector receipt timestamp (UTC) | SPIKE_DM |
| --- | --- | --- | --- |
| 1 | 41347 | 2026-10-16T06:43:44.609418757Z | true |
| 2 | 41347 | 2026-10-16T06:44:14.601636215Z | false |
| 3 | 41347 | 2026-10-16T06:44:44.592132632Z | true |

Test 2 passed the bounded three-cycle criterion; the daemon was left running.
The [proposed startup diff](utils/t2-sigpipe-fix.diff) adds
`signal(SIGPIPE, SIG_IGN)` with failure handling in `main`, before daemonization
and telemetry initialization. It is saved only, not applied or compiled.
The tested wrapper is a validated workaround for this run; the original
untraced exit signal remains uncaptured, so SIGPIPE causation is not proven.
No native credentials were regenerated and no container was restarted.

## Step 12 timestamp test

October 16: PID 41347 remained running throughout this bounded test. No daemon
launch, signal, container restart, credential generation, outage test, or source
patch was executed. Only the report profile was hot-reloaded through RBUS.

The [test profile](utils/t2-spike-profile-ts.json) copies the clean T2Spike
profile with exactly two differences: wrapper hash `t2-spike-step12-ts-v1`
and `JSONEncoding.ReportTimestamp: "Unix-Epoch"`.
The field lookup is `telemetry/source/t2parser/t2parser.c:1757`; accepted
recognized values are `None` at `1464-1466`, `Unix-Epoch` at `1468-1470`,
and `ISO-8601` at `1472-1474`. Unknown strings fall back to None at `1476-1478`.
The setting is stored in `JSONEncoding.tsFormat`
(`telemetry/source/bulkdata/profile.h:36-40`). A production-source search found
only parser assignments/debug output and declarations for `tsFormat`, not an
emission consumer. Report construction in `profile.c:282-292,502,589` adds the
root array and collected parameters, then serializes without report timestamp
insertion. Lowercase per-marker `reportTimestamp` is distinct and was not tested.

Executed timestamp-profile load at `06:48:31 UTC`:

```sh
docker exec native-platform sh -c 'rbuscli setvalues Device.X_RDKCENTRAL-COM_T2.ReportProfiles string "$(cat /mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike-profile-ts.json)"'
```

RBUS returned `setvalues succeeded..`; the persisted profile confirmed the
timestamp setting and test hash. Fresh `SPIKE_MATCH step12-report-timestamp`
was appended to the existing log; DM was set and read as string `false`, and
`/tmp/t2-spike-event` returned `t2_event_s returned 0`.

Actual collector line:

```text
2026-10-16T06:49:00.608333250Z Data received: {"Report":[{"SPIKE_DM":"false"},{"SPIKE_GREP":"21"},{"SPIKE_EVENT":"spike-event-ok"}]}
```

Saved verbatim JSON values in
[received-with-timestamp.json](utils/received-with-timestamp.json), without
inventing a field. **No report timestamp appears in the body.** The prefix is
Docker's UTC RFC 3339/ISO-8601-style receipt-log timestamp with nanosecond
precision, not an emitted Unix-Epoch report timestamp. The grep count is the
actual `21` observed after reload, including pre-existing fixture matches,
not 21 new test triggers. The requested report-level emission did not work.

Clean-profile reload returned success at `06:49:36 UTC`:

```sh
docker exec native-platform sh -c 'rbuscli setvalues Device.X_RDKCENTRAL-COM_T2.ReportProfiles string "$(cat /mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike-profile.json)"'
```

Persistence subsequently confirmed hash `t2-spike-step7-clean-v1` and
`ReportTimestamp: "None"`. Collector receipt at `06:50:06.608002503Z` confirmed
continued delivery after restoration with the same daemon alive.
The mock DM value remains string `false`.

### Documentation preservation

Before the split, SETUP.md had 548 lines and EVIDENCE.md did not exist
(0 lines of prior content). A byte-identical copy was made before edits;
both files then hashed to
`53dce42977f488ceed3604e3913eb38b474d3dc5dd80dd3692790a09db247d2f`.
Step 2 was moved unchanged before the Step 3/4 narrative. Reversing only that
move reconstructed the original hash exactly before adding this new evidence.
No original historical paragraph, command, timestamp, hash, or summary row
was removed. SETUP.md is now a 65-line command runbook with six linked known
issues; all original explanatory content remains here. SAMPLES.md annotates
all three actual receipt bodies and documents missing dashboard identity.

Native credential hashes before and after timestamp testing matched:

| File | SHA-256 |
| --- | --- |
| `/opt/certs/client.pem` | `6b46d857503251b5e243e760a3b616e2065d99b9bea3ecf77e69345a6b5d8cbd` |
| `/opt/certs/client.p12` | `27bcba86802cc43c188e47cf5abb34e0faaa3351396ec6bece686f35b115ed62` |

## Step 14 pre-teardown soak state

At the repeatability-check observation on October 16, 2026 (approximately
07:30 UTC), T2 PID `41347` was still running and both containers were Up.
`docker logs --timestamps --since 2026-10-16T06:43:00Z mockxconf`
contained **56** `Data received:` lines. The first was
`2026-10-16T06:43:44.609418757Z`; the last observed was
`2026-10-16T07:29:58.749373961Z`, with body
`{"Report":[{"SPIKE_DM":"false"}]}`. This is a bounded receipt-count
observation, not a claim that every reporting interval delivered all markers.
This entry was recorded before stopping T2 and Compose teardown with
`utils/compose.step4-no-crl.yaml`.

### Fresh-environment attempt and blocker

Step 14 timing was `2026-10-16T07:29:58Z` through
`2026-10-16T07:31:12Z`: **74 seconds**, including prerequisite inspection and
teardown, not a completed setup duration. `uname -m` returned `arm64`.
T2 was sent TERM, remained present after ten seconds, then was sent KILL.
Compose down with the override removed both containers and their network;
the final Compose `ps` contained no containers.

SETUP.md lacked utility provenance, a telemetry checkout command, and a
fresh-container original-artifact backup procedure. Corrections identify the
maintainer-supplied spike bundle and five required utility files, pin the
telemetry revision evidenced in this runbook's referenced history, and add
the backup-only portion of the referenced Step 8 procedure before installation.
No ASan build is required by that new backup command. These additions were
source-inspected but could not be execution-validated.

All six requested file copies (runbook plus five utilities) to
`/Users/prajyusha/t2-fresh` were rejected by the runtime with
`Path is outside workspace root`. A subsequent existence check confirmed the
directory was absent. No clone, full `./build.sh`, fresh Compose up, patched
installation, marker test, three-cycle test, or outage test was run.

| Fresh acceptance criterion | Result |
| --- | --- |
| Both containers Up | Not run; old containers deliberately removed. |
| Collector receipt containing all three markers | Not run. |
| Three cycles on one T2 PID | Not run. |
| Network disconnect caches and replays | Not run. |

To resume at the requested location, the runtime owner must permit file
operations in `~/t2-fresh` (or the requester must authorize an alternative
directory inside the workspace). Do not use old soak receipts as evidence
that the fresh-environment acceptance criteria passed.

## Step 15 close-out

Verification ran from `fresh-run/` on October 19, 2026. The native container's
shared-volume bind mount points to this fresh workspace. These runtime checks
supersede the obsolete Step 14 workspace-boundary status; they do not establish
that `build.sh` completed successfully or prove cross-architecture repeatability.

| Check | Observed result |
| --- | --- |
| Docker | `native-platform` and `mockxconf` running. Collector attached to `docker-device-mgt-service-test_default` with aliases `mockxconf` and `mock-xconf`. |
| Initial daemon | PID 12537 alive; SIGTERM did not stop it. Relaunched with the runbook SIGPIPE-ignore wrapper after SIGKILL; replacement PID 16315. No container recreation. |
| Receipt rate | October 19, 13:26:00–13:36:00 UTC: **0 / 20** collector `Data received:` lines. All 20 scheduled attempts at `:26` and `:56` seconds logged curl error 60. |
| TLS evidence | Direct verified curl failed with `SSL certificate problem: certificate has expired`. Client expired October 17 at 07:45:44 UTC; collector expired October 17 at 07:46:12 UTC. |
| Replay | **FAIL** after one outage retest. Reconnected October 19 at 13:37:32 UTC; at 13:38:13, zero collector receipts since reconnection. T2 logged curl error 60 at 13:37:59.829 and cached five reports. `ls -la /opt/.t2cachedmessages` showed `T2Spike`, 292 bytes; cache is not empty. Historical October 16 CACHED receipts are not current acceptance evidence. |
| Cleanup | `Device.X_RDK_WebConfig.webcfgSubdocForceReset` set to string `false` and read back as `false`. Containers retained; network reconnected with both aliases; PID 16315 alive. |
| Credentials | Before/after SHA-256 hashes match: PEM `c8918dda99276b8a5c73d757c2ecc73dd10d87a47d3879178839fe7bd79a0680`; PKCS#12 `ebc15b5e66d4150834dd8fba5bdf4ce63f53fdc3f6d822072fb42c13fd80d11c`. No regeneration. |
| Ignore file | No workspace-root `.gitignore` exists, so the conditional `fresh-run/` addition is not applicable. |

Representative missing-cycle evidence:

```text
20261019 13:26:26.826 ERROR LOG.RDK.T2- http_pool_post: Failed to establish connection using xPKI certificate: /opt/certs/client.p12, curl failed: 60 (entry 0)
20261019 13:35:56.818 ERROR LOG.RDK.T2- http_pool_post: Failed to establish connection using xPKI certificate: /opt/certs/client.p12, curl failed: 60 (entry 0)
```

## Spike findings and upstream drafts

Read [WRITEUP.md](WRITEUP.md) for the six spike answers, source quick checks,
flow diagram, and collector/dashboard recommendations. The [calloc issue
draft](utils/upstream-issue-calloc.md) and [SIGPIPE issue
draft](utils/upstream-issue-sigpipe.md) are unsubmitted. Step 13 performed only
read-only checks and documentation work; it did not restart T2 or regenerate
credentials. The write-up also identifies the separate latent initialization
audit to file upstream.

## Summary

| Topic | Summary |
| --- | --- |
| Runbook | Ordered setup commands now identify the five required bundle utilities, pinned telemetry checkout, and fresh-container original backup procedure. |
| Evidence | EVIDENCE.md and SAMPLES.md retain history and actual receipt annotations. |
| Step 13 | WRITEUP.md records source checks; two upstream issue drafts are linked above. |
| Step 15 | Fresh-run runtime inspected; receipt rate 0/20 due to expired certificates. One outage retest and T2 relaunch performed; no successful replay acceptance claimed. |

## Step 16 final verification

On October 19, 2026, both containers were recreated from `fresh-run/` using
the documented Compose down/up path with `utils/compose.step4-no-crl.yaml`.
SIGTERM did not stop old T2 PID 16315 after five seconds; SIGKILL was required.
The replacement native bind mount was verified to point to `fresh-run/`.
The native entrypoint imported server CAs and generated/exported the client
chain; the collector reached its HTTPS listen message. RBUS `rtrouted`,
`rfc_provider`, and the WebConfig mock parameter were verified.

The runbook's public server-CA re-export and trust-only refresh succeeded,
followed by authenticated HTTPS curl with TLS verification enabled.
The fresh-container backup captured **46** original artifacts under
`/opt/t2-orig/`; all backup hashes were independently verified.
`sh utils/apply-t2-patch.sh normal` completed with
`STEP10_INSTALLED mode=normal` and normal/non-ASan linkage checks.
T2 was launched using the SIGPIPE-ignore trap wrapper as PID **12546**;
the clean profile loaded successfully and all three markers were triggered.
No full `build.sh` rerun or cross-architecture validation was performed.

### Certificate validity and renewal

Before recreation, native client validity was October 16 at 07:45:44 through
October 17 at 07:45:44 UTC; collector validity was October 16 at 07:46:12
through October 17 at 07:46:12 UTC. Both were expired.

The startup scripts do **not** contain a literal leaf `-days` setting.
`fresh-run/docker-device-mgt-service-test/native-platform/certs.sh:137`
invokes `/etc/pki/scripts/generate_test_rdk_certs.sh --type client --cn "rdkclient"`;
`fresh-run/docker-device-mgt-service-test/mock-xconf/certs.sh:37` invokes
the same generator with `--type server --cn "mockxconf"`.
In both running images, `/etc/pki/scripts/create_leaf_cert.sh:95` sets
`VALIDITY=1`; lines 372–378 pass it to `sign_certificate`, whose
`/etc/pki/scripts/cert_utils.sh:143` uses `-days "${validity}"`, hence **-days 1**.
The optional tracked signing branch uses the same argument at
`cert_utils.sh:532`, but `CA_TRACK` defaults empty at `create_leaf_cert.sh:99`.

| New leaf | Subject CN | notBefore (UTC) | notAfter (UTC) | `-checkend 0` | `-checkend 86400` |
| --- | --- | --- | --- | --- | --- |
| Native `/opt/certs/client.pem` | rdkclient | Oct 19 13:48:03 2026 | Oct 20 13:48:03 2026 | Exit 0: Certificate will not expire | Exit 1: Certificate will expire |
| Collector `/etc/xconf/certs/mock-xconf-server-cert.pem` | mockxconf | Oct 19 13:48:02 2026 | Oct 20 13:48:02 2026 | Exit 0: Certificate will not expire | Exit 1: Certificate will expire |

These leaves are valid now, but a full further 24-hour validity margin is
not available after startup with a one-day default. No TLS bypass was used.
Renewal is container recreation, not an insecure curl flag.

### Three-marker delivery

```text
2026-10-19T13:49:13.811126839Z Data received: {"Report":[{"SPIKE_DM":"true"},{"SPIKE_GREP":"2"},{"SPIKE_EVENT":"spike-event-ok"}]}
20261019 13:49:13.810 INFO     LOG.RDK.T2- Report Sent Successfully over HTTP : 200
```

The actual collector body is saved in
[received-step16-all-markers.json](utils/received-step16-all-markers.json).
PID 12546 remained present at the subsequent check. The observed grep count
is 2, not a claim of two newly injected markers. This receipt has no
report-level timestamp or device identity.

### Ten-minute receipt rate

The fixed window **2026-10-19T13:48:49.177623Z through
2026-10-19T13:58:49.177623Z** contained **20 / 20** collector
`Data received:` lines, excluding the separate HTTPS readiness probe.
The window was independently recounted with Docker's `--since` and `--until`.
There were no missing cycles requiring failure-log attribution.
T2 PID **12546** was present before, during, and after the observation.

All 20 receipt timestamps (UTC, October 19, 2026):

| Cycle | Collector timestamp | Cycle | Collector timestamp |
| --- | --- | --- | --- |
| 1 | 13:49:13.811126839Z | 11 | 13:54:13.820270380Z |
| 2 | 13:49:43.831711214Z | 12 | 13:54:43.824365088Z |
| 3 | 13:50:13.831743464Z | 13 | 13:55:13.822681922Z |
| 4 | 13:50:43.823663505Z | 14 | 13:55:43.823031422Z |
| 5 | 13:51:13.823133672Z | 15 | 13:56:13.824646297Z |
| 6 | 13:51:43.818980213Z | 16 | 13:56:43.822326505Z |
| 7 | 13:52:13.826232047Z | 17 | 13:57:13.820430588Z |
| 8 | 13:52:43.824716297Z | 18 | 13:57:43.832977172Z |
| 9 | 13:53:13.824383838Z | 19 | 13:58:13.820534338Z |
| 10 | 13:53:43.823519172Z | 20 | 13:58:43.824953630Z |

Cycle 1 contains all three markers as shown above; cycles 2–20 contain
`{"Report":[{"SPIKE_DM":"true"}]}`. This is receipt-rate acceptance,
not an assertion that every report repeated the one-shot grep/event markers.

### Single 65-second outage and replay: PASS

The verifier disconnected the collector once, slept 65 seconds, and reconnected
with both `--alias mockxconf --alias mock-xconf`.
Docker network events recorded disconnect at epoch nanoseconds
`1792418330489442342` and connect at `1792418395705062427`, approximately
65.216 seconds apart. No container restart or T2 relaunch occurred during this test.
The disconnected cycles produced curl 6 and two cached bodies:

```text
20261019 13:59:13.789 ERROR    LOG.RDK.T2- http_pool_post: Failed to establish connection using xPKI certificate: /opt/certs/client.p12, curl failed: 6 (entry 0)
20261019 13:59:13.789 INFO     LOG.RDK.T2- Report Cached, No. of reportes cached = 1
20261019 13:59:43.778 ERROR    LOG.RDK.T2- http_pool_post: Failed to establish connection using xPKI certificate: /opt/certs/client.p12, curl failed: 6 (entry 0)
20261019 13:59:43.778 INFO     LOG.RDK.T2- Report Cached, No. of reportes cached = 2
```

After reconnect, the cache checkpoint contained `T2Spike`, 115 bytes, before the
next scheduled successful upload. At that upload:

```text
20261019 14:00:13.829 INFO     LOG.RDK.T2- Report Sent Successfully over HTTP : 200
20261019 14:00:13.829 INFO     LOG.RDK.T2- Trying to send  2 cached reports
20261019 14:00:13.856 INFO     LOG.RDK.T2- Report Sent Successfully over HTTP : 200
20261019 14:00:13.879 INFO     LOG.RDK.T2- Report Sent Successfully over HTTP : 200
2026-10-19T14:00:13.829647005Z Data received: {"Report":[{"SPIKE_DM":"true"}]}
2026-10-19T14:00:13.855866338Z Data received: {"Report":[{"REPORT_TYPE":"CACHED"},{"SPIKE_DM":"true"}]}
2026-10-19T14:00:13.878914838Z Data received: {"Report":[{"REPORT_TYPE":"CACHED"},{"SPIKE_DM":"true"}]}
```

The subsequent `ls -la /opt/.t2cachedmessages` showed only `.` and `..`:
the cache is empty. Collector `StartedAt` remained
`2026-10-19T13:48:02.039194916Z`; T2 remained PID **12546**.
Network inspection confirmed both aliases after reconnect.

The verifier set the WebConfig DM mock back to string `false`, and an independent
`rbuscli getvalues Device.X_RDK_WebConfig.webcfgSubdocForceReset` returned
type `string`, value `false`. The collector subsequently received:

```text
2026-10-19T14:00:43.818762338Z Data received: {"Report":[{"SPIKE_DM":"false"}]}
```

Final native credential SHA-256 values, recorded without publishing keys:

| File | SHA-256 |
| --- | --- |
| `/opt/certs/client.pem` | `66575c99b16dcaeafc7a31ad126fa471f0c5b00d2de5751440b47ba6fc4f4ee6` |
| `/opt/certs/client.p12` | `e02435e96d2051e0172cd0a02cbf86f97cb8036395402de074bfbd54274ac3e7` |

Containers and the daemon are retained. The helper tool shells were cleaned up.
The verification helper is [utils/step16_verify.py](utils/step16_verify.py);
it was run from `fresh-run/`. No third-party package was installed.

## Summary

| Topic | Summary |
| --- | --- |
| Step 16 | Fresh-run post-build startup passed after both-container recreation: verified mTLS, 46-original backup, normal patch, all-marker receipt, 20/20 receipts in ten minutes, and one successful two-report cached replay. PID 12546 retained; DM false; both aliases restored; cache empty. New one-day leaves are valid now but both fail the 24-hour `checkend` margin. Full build and cross-architecture validation remain unproven. |
| Step 14 | Final soak PID 41347 and 56 receipts recorded before teardown. Fresh setup blocked by workspace-root enforcement; all fresh acceptance checks unexecuted. Attempt elapsed 74 seconds on arm64. |
| Step 12 | RBUS timestamp-profile test delivered all markers but no timestamp field. Clean profile restored without daemon relaunch; original history preserved and receipts annotated in SAMPLES.md. |
| Step 11 | SIGPIPE-ignore wrapper passed three collector-confirmed all-marker cycles with unchanged PID 41347. Launch command updated; startup diff saved but not applied. Original exit signal remains unconfirmed. |
| Step 10 procedure | Isolated one-line JSON HTTP initialization patch; credential/backup-preserving installer and bounded reporting harness added. See Step 10 for actual run results and limitations. |
| Step 9 | One traced ASan launch captured a read SEGV at `prepareHttpUrl`, `reportgen.c:1692`, followed by SIGABRT. JSON HTTP allocation leaves the absent optional list uninitialized; a one-line calloc diff is proposed only. All 46 originals restored and hash/link-verified; backup and native credential hashes unchanged; T2 stopped. |
| Step 8 | One debug/ASan rebuild succeeded; sole launch disappeared in cycle 1 without receipts. Cycles 2-5 skipped. Original daemon and 46 backed-up artifacts restored and verified; no ASan/core file:line evidence. Installed commit unknown. |
| Step 7 | Clean three-marker profile reproduced SIGSEGV in `prepareHttpUrl`. Available fault frames and the generated body were saved, with an explicit all-thread-output truncation limitation. The two-profile normal run exited during its first cycle without collector receipts; the workaround and PID-stability checks failed. |
| Step 6 | Clean restart and HTTPS readiness passed; normal T2 exited during its first upload. No three-marker collector receipt or normal-run PID-stability pass. GDB did not reproduce the failure; the saved live stack is not a fault backtrace. |
| Startup order | Build and start only the two requested services; complete certificate exchange, refresh server trust, verify collector HTTPS, then start/load T2. |
| CA refresh | Use the exact trust-only `docker exec` command above after the current server CA export is available; it preserves existing client credentials. |
| Collector | T2 posts to `/dataLakeMockReportProfile` on HTTPS port 50051, not bare `/dataLakeMock`. |
| Recovery | Step 4's collector-only CRL-L3 override bypassed the Step 3 startup blocker. After a trust-only CA refresh, five cached reports replayed with T2 HTTP 200s and matching collector receipts. |
| Outage method | Network disconnect/reconnect produced curl 6 and two cached reports; both replayed after reconnect with HTTP 200s and collector receipts. Keep the collector running and restore the `mockxconf` alias. |
| Cleanup | Step 2 confirmed the mock reset getter was `false`; the old cache included historical `true` values. Step 4 retained T2 PID 2817 and unchanged native client credential hashes; the network is restored and the cache is empty. |
| Step 5 XConf | Legacy T2SpikeXconf response is staged and manually reachable over verified mTLS, but ConfigURL, ModelName, and STB MAC have no RBUS entries. No T2 XConf enablement or attributed report was observed. |
| Step 5 final state | Native credentials are unchanged and both containers remain Up. PID 2817 disappeared after reload; a recovery launch enabled the old JSON profile but exited during upload. T2 is not running; native-provider and daemon-runtime owners must resolve the documented blockers. |
