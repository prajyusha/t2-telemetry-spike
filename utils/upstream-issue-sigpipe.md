# Draft upstream issue: suspected SIGPIPE during normal HTTP upload

## Target and confidence

Target repository: `rdkcentral/telemetry`. Suggested title: “Investigate normal upload exits with CURLOPT_NOSIGNAL; SIGPIPE-ignore launch survives.” This is an unsubmitted investigation draft, not a confirmed SIGPIPE root-cause report. Baseline checkout is `a2f2a545e4bd6170eac96f7c0c46fbd4df6f1654`; the original installed commit is unknown. See [write-up](../WRITEUP.md) and [Step 11 evidence](../EVIDENCE.md#step-11-sigpipe-ignore-launch).

## Reproduction and observed comparison

Use a separate disposable native-platform environment with the JSON HTTP allocation fix installed, no ASan linkage, the [clean profile](t2-spike-profile.json), and the existing authenticated HTTPS collector on `https://mockxconf:50051/dataLakeMockReportProfile`. After profile activation, trigger the log, event and DM markers as in [SETUP.md](../SETUP.md), and observe the daemon PID and collector at each 30-second cycle.

The prior ordinary normal-build demo exited during its first upload cycle: [t2-step10-demo-results.json](t2-step10-demo-results.json) records PID 39303 absent and no receipt. No exit signal was captured, so this does not itself prove SIGPIPE. Debugger runs behaved differently; the daemon forks unconditionally (`telemetry/source/telemetry2_0.c:329-355`), with no verified foreground option.

The separately authorized comparison used this inherited signal-disposition workaround:

```sh
docker exec -d native-platform sh -c "trap '' PIPE; exec /usr/local/bin/telemetry2_0"
```

Step 11 then recorded the same PID 41347 and three actual all-marker collector receipts at `2026-10-16T06:43:44.609418757Z`, `06:44:14.601636215Z`, and `06:44:44.592132632Z`. Expected DM values were true, false, true; grep was `"1"` and event was `"spike-event-ok"`. This strongly indicates SIGPIPE involvement but does not capture the original failing signal or identify a particular socket/TLS write.

Do not execute either launch or any restart against the preserved demo. Step 13 is documentation/source review only.

## Source evidence

`init_connection_pool`, `telemetry/source/protocol/http/multicurlinterface.c:373`, sets:

```c
CURL_SETOPT_CHECK(pool_entries[i].easy_handle, CURLOPT_NOSIGNAL, 1L);
```

`t2DaemonMainModeInit`, `telemetry/source/telemetry2_0.c:228-234`, registers other signals, not SIGPIPE:

```c
sigaction(SIGINT, &act, NULL);
sigaction(SIGTERM, &act, NULL);
sigaction(SIGUSR1, &act, NULL);
sigaction(LOG_UPLOAD, &act, NULL);
sigaction(EXEC_RELOAD, &act, NULL);
sigaction(LOG_UPLOAD_ONDEMAND, &act, NULL);
sigaction(SIGIO, &act, NULL);
```

No SIGPIPE registration was found in the searched production source/include trees; a handler mention is not registration. NOSIGNAL plus the controlled wrapper result motivates a defensive startup policy, but is not a signal capture.

## Proposed diff

The existing [t2-sigpipe-fix.diff](t2-sigpipe-fix.diff), relative to the telemetry repository, inserts failure-checked handling after `LOGInit()` in `main`, before daemonization and telemetry initialization:

```diff
diff --git a/source/telemetry2_0.c b/source/telemetry2_0.c
--- a/source/telemetry2_0.c
+++ b/source/telemetry2_0.c
@@ -330,6 +330,14 @@ int main()
 {
     pid_t process_id = 0;
     pid_t sid = 0;
     LOGInit();
 
+    /* Keep broken upload connections from terminating the daemon. */
+    if (signal(SIGPIPE, SIG_IGN) == SIG_ERR)
+    {
+        perror("Failed to ignore SIGPIPE");
+        return 1;
+    }
+
+
     /* Abort if another instance of telemetry2_0 is already running */
```

This saved proposal has not been applied or compiled. The shell wrapper was tested; the source diff was not. The process-wide policy also affects inherited subprocess dispositions and needs upstream review. It should allow transport failures to reach normal failure/cache handling rather than claiming success.

## Upstream verification needed

In a separately authorized disposable reproduction, capture SIGPIPE and its stack/exit status during the failing ordinary upload. Compare otherwise identical launches with default and ignored disposition, holding the calloc fix constant. Exercise broken peer connections and verify PID survival, failed-upload caching, and collector-confirmed replay, as well as normal uploads and shutdown. These are proposed upstream checks, not Step 13 tests or acceptance claims.

## Summary

| Topic | Summary |
| --- | --- |
| Observation | Ordinary demo exited; ignored-SIGPIPE wrapper survived three delivered cycles. |
| Confidence | SIGPIPE strongly indicated, original signal and write-site not captured. |
| Proposal | Early failure-checked ignore policy; diff saved only, not compiled or applied. |
