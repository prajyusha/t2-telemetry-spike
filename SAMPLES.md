# T2 collector receipt annotations

These are actual collector bodies, not locally generated reports. See the
[runbook](SETUP.md) and [step-by-step evidence](EVIDENCE.md).
Profile settings refer to `profiles[0].value` in the
[clean profile](utils/t2-spike-profile.json), except where the
[timestamp-test profile](utils/t2-spike-profile-ts.json) is explicitly named.
All marker values in these bodies are JSON strings, including booleans and counts.

## All three markers

Saved body: [received-all-markers.json](utils/received-all-markers.json).

| Field name | Example value | Source | Meaning | Controlling profile setting |
| --- | --- | --- | --- | --- |
| `Report` | Array of three single-field objects | T2-added | Root array for NameValuePair output; these entries belong to one report. | `RootName: "Report"`, `EncodingType: "JSON"`, `JSONEncoding.ReportFormat: "NameValuePair"` |
| `Report[0].SPIKE_DM` | `"true"` | data model | String value read from the WebConfig mock reset parameter; not a physical device state or identity. | `Parameter[type=dataModel].name: "SPIKE_DM"`, `reference: "Device.X_RDK_WebConfig.webcfgSubdocForceReset"`, `reportEmpty: true` |
| `Report[1].SPIKE_GREP` | `"1"` | grep | Count of matching `SPIKE_MATCH` log lines collected for this report, serialized as a string. | `Parameter[type=grep].marker: "SPIKE_GREP"`, `search: "SPIKE_MATCH"`, `logFile: "/mnt/L2_CONTAINER_SHARED_VOLUME/utils/t2-spike.log"`, `use: "count"`, `reportEmpty: true` |
| `Report[2].SPIKE_EVENT` | `"spike-event-ok"` | event | Absolute string payload sent by `utils/t2-spike-event.c` through `t2_event_s`. | `Parameter[type=event].name/eventName: "SPIKE_EVENT"`, `component: "t2_spike"`, `use: "absolute"`, `reportEmpty: true` |

Array indices describe this saved body, not a stable dashboard schema.
`ReportingInterval: 30` controls scheduled collection, not a field in the body.
The clean profile has `JSONEncoding.ReportTimestamp: "None"`; no report timestamp
or device identifier appears in this receipt.

### Step 16 fresh-run receipt

After authorized container recreation and normal patch installation, the collector
logged this actual receipt on October 19, 2026:

```text
2026-10-19T13:49:13.811126839Z Data received: {"Report":[{"SPIKE_DM":"true"},{"SPIKE_GREP":"2"},{"SPIKE_EVENT":"spike-event-ok"}]}
```

The body is saved separately in
[received-step16-all-markers.json](utils/received-step16-all-markers.json).
The same field annotations above apply, except the observed grep count is `2`.
This does not mean two newly injected Step 16 markers: the fresh-run log already
contained a match before this run appended its marker. No timestamp or device
identity has been added. See [Step 16 results](EVIDENCE.md#step-16-final-verification)
for the independent receipt-rate and outage checks.

## Cached replay

Saved body: [received-cached-replay-2.json](utils/received-cached-replay-2.json).
The [Step 4 history](EVIDENCE.md#step-4-collector-only-crl-l3-override)
records five collector-confirmed cached replays after recovery.

| Field name | Example value | Source | Meaning | Controlling profile setting |
| --- | --- | --- | --- | --- |
| `Report` | Array of two single-field objects | T2-added | Root array containing a replay tag and the retained original measurement. | `RootName: "Report"`, `JSONEncoding.ReportFormat: "NameValuePair"` |
| `Report[0].REPORT_TYPE` | `"CACHED"` | T2-added | Report was tagged for caching after an upload failure, then received on replay. It is not a new read of the mock state. | No explicit profile switch; automatic failed-upload caching for the profile's `Protocol: "HTTP"` destination. |
| `Report[1].SPIKE_DM` | `"true"` | data model | Historical mock reset value from original collection; it need not match the value at replay time. | `Parameter[type=dataModel].name: "SPIKE_DM"`, `reference: "Device.X_RDK_WebConfig.webcfgSubdocForceReset"` |

`tagReportAsCached` adds the replay tag in
`telemetry/source/reportgen/reportgen.c:1791-1826`; failed-send handling calls it
in `telemetry/source/bulkdata/profile.c`. This receipt contains neither grep nor
event measurements; do not synthesize them from other receipts. It also contains
no original collection time, replay time, or device identity. Collector log time
is external evidence, not an extra JSON field.

## ReportTimestamp test

Saved body: [received-with-timestamp.json](utils/received-with-timestamp.json).
Despite its requested filename, this is a receipt from a timestamp-enabled test,
**not a receipt containing a timestamp**.

The collector log line at `2026-10-16T06:49:00.608333250Z` contained exactly:
`{"Report":[{"SPIKE_DM":"false"},{"SPIKE_GREP":"21"},{"SPIKE_EVENT":"spike-event-ok"}]}`.
The leading time is Docker's UTC RFC 3339/ISO-8601-style timestamp with nanosecond
fraction and `Z`; it is outside the report body. No Unix-Epoch field or value
appears anywhere in that JSON.

| Field name | Example value | Source | Meaning | Controlling profile setting |
| --- | --- | --- | --- | --- |
| `Report` | Array of three single-field objects | T2-added | Root array; no timestamp entry was added. | Timestamp-test `RootName: "Report"`, `JSONEncoding.ReportFormat: "NameValuePair"` |
| `Report[0].SPIKE_DM` | `"false"` | data model | Mock value set and verified for this test. | Timestamp-test data-model `name: "SPIKE_DM"` and WebConfig `reference`, `reportEmpty: true` |
| `Report[1].SPIKE_GREP` | `"21"` | grep | Actual observed match count after profile reload and fresh input; not a Unix timestamp. The count includes existing fixture matches and is not evidence of 21 new Step 12 inputs. | Timestamp-test grep `marker: "SPIKE_GREP"`, `search: "SPIKE_MATCH"`, shared `logFile`, `use: "count"` |
| `Report[2].SPIKE_EVENT` | `"spike-event-ok"` | event | Absolute event payload triggered after timestamp-profile activation. | Timestamp-test event `name/eventName: "SPIKE_EVENT"`, `component: "t2_spike"`, `use: "absolute"` |

The test profile differs from the clean profile only in wrapper `hash`
(`t2-spike-step12-ts-v1`) and `JSONEncoding.ReportTimestamp: "Unix-Epoch"`.
`telemetry/source/t2parser/t2parser.c:1757` reads `ReportTimestamp`;
lines `1464-1478` recognize `None`, `Unix-Epoch`, and `ISO-8601`, with unknown
strings mapped to None. `telemetry/source/bulkdata/profile.h:36-40` stores
`tsFormat`, but the searched production source has no read applying it to
report generation. `profile.c:282-292,502,589` constructs the root, collects
parameters and serializes the JSON without adding a report-level timestamp.
Per-marker lowercase `reportTimestamp` handling is a separate feature and was
not enabled or substituted for this test.

The clean profile was reloaded through RBUS at `06:49:36 UTC`, without restarting
PID 41347. The test therefore establishes parser acceptance and delivery, but
**fails the expected report-level timestamp emission**.

## Missing dashboard context

| Missing field/context | Consequence | Profile/provider requirement |
| --- | --- | --- |
| Device ID | Cannot reliably group reports by device. | Add an explicitly sourced identity parameter; no device ID is configured here. |
| MAC | Cannot correlate with a network/device inventory. | Add a data-model parameter backed by a working MAC provider; Step 5's STB MAC lookup failed. |
| Model | Cannot group by hardware model. | Add a model data-model parameter with a working provider; Step 5's ModelName lookup failed. |
| Firmware | Cannot correlate behavior with software release. | Add a firmware parameter with a working provider; none is configured in the JSON profile. |
| Collection timestamp | Cannot place cached measurements accurately on a time series. | Report-level setting did not emit a field in this test; requires separately scoped implementation or a verified alternative. |
| Collection vs receipt time | Replay arrival can be mistaken for fresh measurement time. | Preserve external collector receipt time separately; do not fabricate collection time from it. |

Step 5's manual XConf response did not enable a T2 XConf profile and is not
evidence of identifiers in these receipts.

## Summary

| Topic | Summary |
| --- | --- |
| All-marker sample | One delivered report contains data-model, grep-count and absolute-event strings. |
| Cached sample | T2 adds `REPORT_TYPE=CACHED`; the retained DM measurement is historical. |
| Timestamp test | Unix-Epoch is accepted but no timestamp is emitted; log timestamp is external metadata. |
| Dashboard readiness | Device ID, MAC, model, firmware and trustworthy collection time are absent. |
