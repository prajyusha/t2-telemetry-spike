# Draft upstream issue: initialize optional HTTP URI list in JSON profiles

## Target and scope

Target repository: `rdkcentral/telemetry`. Suggested title: “JSON HTTP profile without RequestURIParameter can crash prepareHttpUrl through uninitialized list pointer.” This is an unsubmitted issue draft. Source baseline is `a2f2a545e4bd6170eac96f7c0c46fbd4df6f1654`; the original installed binary's commit is unknown. See [write-up](../WRITEUP.md) and [Step 9 evidence](../EVIDENCE.md#step-9-single-run-asan-diagnosis).

## Reproduction

In a separate disposable native-platform test environment, build the baseline with ASan and debug symbols, load [the clean fixture](t2-spike-profile.json), and allow its 30-second reporting interval. It specifies HTTP but omits optional `HTTP.RequestURIParameter`. The JSON load command is:

```sh
docker exec native-platform sh -c 'rbuscli setvalues Device.X_RDKCENTRAL-COM_T2.ReportProfiles string "$(cat /mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike-profile.json)"'
```

After activation, append one fresh `SPIKE_MATCH` log line, set/read the mock DM field, and run the [event sender](t2-spike-event.c), as detailed in [SETUP.md](../SETUP.md). Observe the first generated report/upload. Do not run this reproduction against the preserved demo or restart it. The historical ASan launch and exact diagnostic settings are retained in [t2-step9-evidence.txt](t2-step9-evidence.txt).

Expected behavior is safe URL preparation with no optional URI parameters. Observed behavior was a read SEGV followed by ASan abort before collector delivery.

## Evidence and source diagnosis

[The actual ASan report](t2-asan-report.txt) records:

```text
#0 prepareHttpUrl /opt/t2-debug-src/source/reportgen/reportgen.c:1692
#1 CollectAndReport /opt/t2-debug-src/source/bulkdata/profile.c:689
SUMMARY: AddressSanitizer: SEGV .../source/reportgen/reportgen.c:1692
```

The [exit trace](t2-step9-strace.txt) records SIGSEGV, then SIGABRT. Only four fault-stack frames were emitted; thread-creation stacks are not additional fault frames. No collector receipt was observed. This is not a demonstrated use-after-free, and no debugger dump of the pointer variable was captured.

`processConfiguration`, `telemetry/source/t2parser/t2parser.c:1859-1865`, allocates the separate destination without clearing it:

```c
profile->t2HTTPDest = (T2HTTP *) malloc(sizeof(T2HTTP));
```

`protocolSet`, same source at `1497-1508`, initializes URL, Compression and Method, but creates the list only inside:

```c
if(jprofileHTTPRequestURIParameter)
{
    Vector_Create(&(profile->t2HTTPDest->RequestURIparamList));
```

`prepareHttpUrl`, `telemetry/source/reportgen/reportgen.c:1692`, already has a NULL guard:

```c
if (http->RequestURIparamList && http->RequestURIparamList->count)
```

An indeterminate non-NULL member can pass that guard and fault on count. Zeroing the enclosing Profile does not initialize the separately allocated destination. The source and ASan evidence support the initialization defect; adding another NULL guard is insufficient.

## Proposed diff and validation status

Apply this existing [proposal](t2-prepareHttpUrl-fix.diff) relative to the telemetry repository:

```diff
--- a/source/t2parser/t2parser.c
+++ b/source/t2parser/t2parser.c
@@ -1858,7 +1858,7 @@
 
     if((strcmp(jprofileProtocol->valuestring, "HTTP") == 0))
     {
-        profile->t2HTTPDest = (T2HTTP *) malloc(sizeof(T2HTTP));
+        profile->t2HTTPDest = (T2HTTP *) calloc(1, sizeof(T2HTTP));
     }
     else if ((strcmp(jprofileProtocol->valuestring, "RBUS_METHOD") == 0))
     {
```

The patch was subsequently installed in the isolated `/opt/t2-patched-src` build, not the host checkout. Step 11's normal build with the SIGPIPE-ignore wrapper achieved three all-marker collector receipts; this validates the combined setup, not proof that all independent exit causes are fixed. Step 10's ordinary demo disappeared, as [its results](t2-step10-demo-results.json) show.

Upstream regression coverage should exercise omitted, empty, and populated RequestURIParameter and allocation failure under sanitizers, plus safe cleanup. No new regression tests were executed in Step 13.

## Related initialization audit

Track separately the malloc-allocated `T2RBUS.rbusMethodParamList` (`t2parser.c:1865`, conditional vector creation at `1575`) and `EventMarker.accumulatedTimestamp` (`:254,295-297`). `freeEMarker` reads the latter before checking timestamp format (`telemetry/source/utils/t2common.c:158`). These are latent source findings, not reproduced HTTP-spike crash causes. They require a separate upstream issue/audit rather than silently broadening this minimal diff.

## Summary

| Topic | Summary |
| --- | --- |
| Failure | ASan captured a read SEGV in prepareHttpUrl before delivery. |
| Proposal | Zero-initialize JSON T2HTTP so an absent optional list is NULL. |
| Status | Draft only; isolated patch installed previously, host source unchanged. |
