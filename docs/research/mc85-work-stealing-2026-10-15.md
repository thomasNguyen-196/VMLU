# MC-85 execution scheduler amendment — 2026-10-15

The user requested pausing MiMo V2.6 Flash and allowing idle workers to help
other lanes. The original measurement card describes fixed lanes without
work stealing; that historical card and condition hashes remain frozen.
This amendment records the authorized execution change, not a claim that the
whole campaign used the same scheduler.

The process was stopped with 9,102 of 10,136 Dev/Test items complete, leaving
1,034 items (including five technical failures). Main remains complete at
2,043 items. Requests interrupted by stopping may have consumed provider
tokens without producing a durable terminal result; they remain unfinished.

On the next explicit execution, MC-85 uses `lane-work-stealing-v1` with at
most 12 concurrent requests. Each worker consumes its own pending lane first;
when empty, it claims the next unstarted item from the longest pending lane.
Claims are serialized under a lock. In-flight items cannot be stolen. Each
unfinished item receives at most one attempt per pass; transient failures
remain available to the existing bounded recovery passes. Fatal failures
still stop further claims; already in-flight calls may finish.

Original `shard` and `lane` retain item assignment identity. New attempts add
`worker_shard`, `worker_lane`, and `scheduler` to identify actual execution.
Execution history records the scheduler and current shared runner hash;
the runner sources are archived on execution. Frozen model, prompts, input
manifests, scoring, temperature, default reasoning, 20k budget and completed
answers are preserved. Other campaigns retain fixed lanes by default.

The campaign is left paused after configuration and offline verification.
The next execution resumes the existing output automatically:

```bash
.venv/bin/python -m code_benchmark.run_mimo26_direct_20k_mc85 --execute
```

Verification includes a blocked owner whose remaining item is claimed by an
idle worker, original-versus-actual lane provenance, no duplicate attempts in
a pass, and resume retrying only the technical failure. No live endpoint
calls are required to configure this scheduler.
