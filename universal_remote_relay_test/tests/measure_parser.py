"""Opt-in synthetic parser comparison inside the ARM image; no device traffic.

Run each engine in a fresh process using PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION.
The workflow runs this with networking disabled. QEMU results are not Pi RAM
measurements or an overnight stability test.
"""

from __future__ import annotations

import gc
import json
import resource
import sys
import time
from pathlib import Path

# In the image the complete service dependency graph lives in /app.
sys.path.insert(0, "/app")
import service  # noqa: F401
from androidtvremote2.remotemessage_pb2 import (
    RemoteDirection,
    RemoteKeyCode,
    RemoteMessage,
)
from google.protobuf.internal import api_implementation


def resident_kib() -> int:
    gc.collect()
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    raise RuntimeError("Linux resident memory counter is unavailable")


imported_rss = resident_kib()
message = RemoteMessage()
message.remote_key_inject.key_code = RemoteKeyCode.KEYCODE_DPAD_UP
message.remote_key_inject.direction = RemoteDirection.SHORT
payload = message.SerializeToString()
count = 200_000
started = time.perf_counter()
for _ in range(count):
    decoded = RemoteMessage()
    decoded.ParseFromString(payload)
    if decoded.remote_key_inject.key_code != RemoteKeyCode.KEYCODE_DPAD_UP:
        raise RuntimeError("Parser returned the wrong command")
elapsed = time.perf_counter() - started
print(
    json.dumps(
        {
            "method": "synthetic ARM64 image under QEMU; same dependencies",
            "engine": api_implementation.Type(),
            "import_rss_mib": round(imported_rss / 1024, 3),
            "final_rss_mib": round(resident_kib() / 1024, 3),
            "peak_rss_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3
            ),
            "parse_count": count,
            "parse_seconds": round(elapsed, 4),
        }
    )
)
