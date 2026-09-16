---
sidebar_position: 4.5
title: Binary datapoint frames
description: The wire format of POST /timeseries/data/binary, the high-throughput datapoint insert, for anyone producing frames outside the Java SDK.
---

# Binary datapoint frames

`POST /timeseries/data/binary` is the high-throughput form of
[`POST /timeseries/data`](./timeseries#write-datapoints). The body is one or more
**datapoint frames**: a 28-byte envelope, a directory of the series in the frame, and a
zstd-compressed Arrow IPC stream in one canonical schema per value type, rows sorted by series
and timestamp. Nothing is parsed as text, so a request carries up to a million points in a few
megabytes.

The Java SDK builds frames for you, see [binary ingest](./timeseries#binary-ingest). This page
is the byte-level contract for everyone else: a Python or Rust producer with pyarrow or arrow-rs,
or a gateway forwarding frames it did not build. The Python and Rust SDKs do not have a binary
method yet.

| | |
| --- | --- |
| Method and path | `POST /timeseries/data/binary` |
| `Content-Type` | `application/vnd.intellistream.datapoint-block` |
| `Content-Encoding` | None (or `identity`). Compression lives inside each frame; any other body-level encoding is a `415`. |
| Body | One or more frames back to back, the last ending exactly at the end of the body. |
| Success | `204`, no body. Every frame in the request was validated and published. |
| Failure | An [`application/problem+json`](#responses) document, and **nothing** was inserted. |

## The envelope {#envelope}

All integers are little-endian.

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | Magic, the ASCII bytes `DHDP`. |
| 4 | 1 | Version, `1`. |
| 5 | 1 | Value type id: `1` bigint, `2` float, `3` numeric, `4` text, `5` decimal32, `6` mixed, `7` float32. |
| 6 | 1 | Codec, `1` = Arrow IPC stream. `0` is reserved. |
| 7 | 1 | Compression, `1` = zstd. Required: `0` is refused with `uncompressed-frame`. |
| 8 | 4 | `u32` row count, at least 1. |
| 12 | 4 | `u32` series count, the number of distinct series ids in the payload. |
| 16 | 4 | `u32` directory length in bytes. |
| 20 | 4 | `u32` payload length in bytes, as carried (compressed). |
| 24 | 4 | `u32` payload length in bytes after decompression. |
| 28 | | The [directory](#directory), then the [payload](#payload). |

The zstd level is the sender's choice. The API decompresses the payload into exactly the
declared number of bytes, and a stream that ends early or runs long is refused.

## The directory {#directory}

Series count entries, each an `int64` series id, a `varuint` byte length, then that many bytes
of UTF-8 external id (1 to 1 024 bytes). `varuint` is unsigned LEB128: seven bits per byte, low
group first, high bit set on every byte but the last.

Ids are **strictly ascending** and must be exactly the set of ids in the payload. The directory
is left uncompressed so the API can read which series a frame touches without touching the
payload.

Series are named by their **internal id**, which is why a producer looks them up first.
`POST /timeseries/byids` returns `id` (a JSON string, see
[entity ids](./client#results--errors)), `externalId` and `valueType` for each external id. The
external id you write into the directory is checked against the series on every request, which
is how a renamed or recreated series is caught: a mismatch is a `422` telling you to refresh your
cache, not a silent write into the wrong series.

:::note Read access as well as write
`/timeseries/byids` omits series in data sets you cannot **read**, so a binary producer needs
read and write on the data set. The JSON path names series by external id and needs write
alone. See [access control](./datasets#access-control).
:::

## The payload {#payload}

One zstd frame containing one Arrow IPC **stream**: one schema message, one or more record
batches, and the end-of-stream marker, with nothing after it. Little-endian throughout.

The stream is read by a minimal codec that accepts exactly the subset a plain writer emits and
refuses the rest, with the `reason` on the right:

| Rule | `reason` |
| --- | --- |
| Every message uses the continuation-marker framing (`0xFFFFFFFF`, then the metadata length), metadata version V4 or newer. | `payload-invalid` |
| Exactly one schema message, before any record batch, with no body. | `payload-invalid` |
| The schema matches the [canon](#schemas) for the frame's value type: field count, names, types with their parameters, nullability; no dictionary encoding, no children. Custom metadata is ignored. | `schema-mismatch` |
| No dictionary batches; record batch bodies are not compressed in-band; no variadic buffers. | `payload-invalid` |
| Buffers lie inside the body, 8-byte aligned; a non-nullable field declares zero nulls; `Utf8` offsets never decrease or run past the data. | `payload-invalid` |
| Nothing after the end-of-stream marker. | `trailing-bytes` |
| The rows of all batches add up to the envelope's row count. | `row-count-mismatch` |
| Rows are sorted by `(timeseries_id, timestamp)` ascending across the whole frame. | `unsorted` |
| No two rows share a `(timeseries_id, timestamp)`. | `duplicate-row` |
| A text value is valid UTF-8, at most 64 characters and 256 bytes; a decimal fits its precision; a `mixed` row sets exactly one of its two value columns. | `value-invalid` |

Timestamps are epoch milliseconds, UTC. There is no seconds heuristic: the type is
unambiguous, so a millisecond value is taken as given.

### Canonical schemas {#schemas}

Every frame starts with the same two fields, then one value field decided by the envelope's
value type (two for `mixed`):

| Field | Arrow type | Nullable |
| --- | --- | --- |
| `timeseries_id` | `Int64` | no |
| `timestamp` | `Timestamp(MILLISECOND, "UTC")` | no |

| Value type | Value field(s) |
| --- | --- |
| `bigint` | `value: Int64` |
| `float` | `value: Float64` |
| `float32` | `value: Float32` |
| `numeric` | `value: Decimal128(18, 6)` |
| `decimal32` | `value: Decimal128(9, 4)` |
| `text` | `value: Utf8` |
| `mixed` | `value_numeric: Float64` nullable and `value_text: Utf8` nullable, exactly one set per row |

The timestamp's unit and zone must be exactly `MILLISECOND` and `"UTC"`, and the decimals must
be 128-bit with exactly that precision and scale. These are the storage types, which is why the
server casts nothing on the way in. See [value types](./timeseries#value-types) for which type
to give a series.

## Caps {#caps}

Fixed in the format, not deployment policy, except the last row:

| Cap | Value | Over it |
| --- | --- | --- |
| Rows per frame, numeric types | 100 000 | `400 row-count-mismatch` |
| Rows per frame, `text` or `mixed` | 10 000 | `400 row-count-mismatch` |
| Series per frame | 10 000 | `400 directory-invalid` |
| External id in the directory | 1 024 bytes | `400 directory-invalid` |
| Text value | 64 characters and 256 bytes | `400 value-invalid` |
| Decompressed payload per frame | 4 MiB | `413 frame-too-large` |
| Frames per request | 32 | `413 too-many-frames` |
| Decompressed total per request | 64 MiB | `413 request-too-large` |
| Compressed body per request | 64 MiB by default, `datahub.limits.max-body-bytes-datapoints-binary` | `413 request-too-large` |

A frame is published as one message, so the 4 MiB keeps it under the broker's limit with room
to spare. 100 000 float points are about 2.4 MB decompressed and a few hundred KB compressed, so
a full frame is comfortably inside it; a producer only needs to split on the row cap.

## Responses {#responses}

Every refusal is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem document of
`type: "https://intellistream.ai/errors/datapoint-block-rejected"` with a stable `reason`, plus
`frameIndex` (0-based) when one frame is at fault and `timeseriesIds` when particular series are:

```json
{
  "type": "https://intellistream.ai/errors/datapoint-block-rejected",
  "title": "Datapoint block rejected",
  "status": 422,
  "detail": "2 series in frame 3 have a different external id than the directory says; refresh the client's series cache.",
  "reason": "external-id-mismatch",
  "frameIndex": 3,
  "timeseriesIds": [1041, 1042]
}
```

| Status | `reason` | Meaning |
| --- | --- | --- |
| `204` | | Accepted and published. |
| `400` | `malformed-frame`, `unsupported-version`, `unsupported-codec`, `unknown-value-type`, `uncompressed-frame`, `trailing-bytes`, `directory-invalid`, `payload-invalid`, `schema-mismatch`, `row-count-mismatch`, `unsorted`, `duplicate-row`, `value-invalid` | The frame at `frameIndex` breaks the format; `detail` says where. Fix the producer. |
| `403` | | The caller lacks write on a series' data set. The usual [data set `403`](./datasets#access-control), not this problem type. |
| `404` | `unknown-timeseries` | `timeseriesIds` do not exist in this tenant. Re-resolve them. |
| `413` | `frame-too-large`, `too-many-frames`, `request-too-large` | Over a [cap](#caps). Split; a retry as-is never succeeds. |
| `415` | `unsupported-content-encoding` | A `Content-Encoding` header. The wrong `Content-Type` is also a `415`, from the framework, without a `reason`. |
| `422` | `value-type-mismatch` | `timeseriesIds` in `frameIndex` have another value type than the envelope declares. |
| `422` | `external-id-mismatch` | `timeseriesIds` in `frameIndex` have another external id than the directory says. Drop them from your cache and resolve again. |
| `429` | `too-many-in-flight` | This API instance is already validating its limit of binary requests; `Retry-After` is one second. |
| `429` | | The ordinary [rate limit](./limits#rate-limits) or [daily quota](./limits#daily-ingest-quotas), with their own `type`. |

### Retrying {#retrying}

Every frame is validated before any is published, so a rejected request inserted **nothing** and
is retried **as a whole**. Datapoints are keyed by `(series, timestamp)`, so replaying a request
that did reach the store, say after a lost response, is harmless.

- `429` with `Retry-After`, `5xx` and a dropped connection: wait and resend the same body.
- `404 unknown-timeseries` and `422 external-id-mismatch`: forget the named ids, look them up
  again by external id, rebuild the frames and resend once. If it fails the same way, the series
  really is gone.
- Everything else: fix the request. The Java SDK handles all three for you.

Quotas are charged after validation, so a refused request costs nothing. The
[`ingested bytes`](./limits#daily-ingest-quotas) quota counts **decompressed** bytes on this
path: compressing harder does not stretch the allowance.

## Producing frames from pyarrow {#pyarrow}

:::info Needs a sandbox
The example writes into `engine_temperature`, which section **A** of
[Seed a sandbox](/guides/seed-a-sandbox) creates.
:::

An IPC stream written by pyarrow or arrow-rs with the schema above, no in-band compression and
no dictionary encoding is exactly what the codec accepts. What is left is the envelope and the
zstd wrap. The example resolves the series, picks the schema its value type calls for, writes an
hour of readings and reads them back:

```python
import struct
import pyarrow as pa, pyarrow.ipc as ipc, requests, zstandard

BASE, HEADERS = "https://api.intellistream.ai", {"Authorization": "Bearer ..."}
CANON = {"float": (2, pa.float64()), "float32": (7, pa.float32()), "bigint": (1, pa.int64())}

# 1. Resolve the series: internal id, external id and value type. Needs read on its data set.
found = requests.post(f"{BASE}/timeseries/byids", headers=HEADERS,
                      json={"items": [{"externalId": "engine_temperature"}]}).json()["items"][0]
sid, ext = int(found["id"]), found["externalId"].encode()
type_id, value_type = CANON[found["valueType"]]

# 2. One record batch in that canon, sorted by (timeseries_id, timestamp).
schema = pa.schema([
    pa.field("timeseries_id", pa.int64(), nullable=False),
    pa.field("timestamp", pa.timestamp("ms", tz="UTC"), nullable=False),
    pa.field("value", value_type, nullable=False)])
t0, rows = 1_767_139_200_000, 3600                    # 2025-12-31T00:00:00Z, one reading a second
table = pa.table({
    "timeseries_id": pa.array([sid] * rows, pa.int64()),
    "timestamp": pa.array([t0 + i * 1000 for i in range(rows)], pa.timestamp("ms", tz="UTC")),
    "value": pa.array([88.0 + (i % 40) / 10 for i in range(rows)], value_type),
}, schema=schema).sort_by([("timeseries_id", "ascending"), ("timestamp", "ascending")])

# 3. The IPC stream, then zstd around it.
sink = pa.BufferOutputStream()
with ipc.new_stream(sink, schema) as writer:          # default options: no in-band compression
    writer.write_table(table)
raw = sink.getvalue().to_pybytes()
payload = zstandard.ZstdCompressor(level=9).compress(raw)

# 4. Directory and envelope.
def varuint(n):
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)

directory = struct.pack("<q", sid) + varuint(len(ext)) + ext
envelope = (b"DHDP" + bytes([1, type_id, 1, 1])        # version 1, value type, Arrow IPC, zstd
            + struct.pack("<IIIII", rows, 1, len(directory), len(payload), len(raw)))

r = requests.post(f"{BASE}/timeseries/data/binary", data=envelope + directory + payload,
                  headers={**HEADERS, "Content-Type": "application/vnd.intellistream.datapoint-block"})
assert r.status_code == 204, r.text

# 5. Read the hour back.
got = requests.post(f"{BASE}/timeseries/data/list", headers=HEADERS,
                    json={"items": [{"externalId": "engine_temperature", "start": t0,
                                     "end": t0 + rows * 1000, "limit": 10_000}]}).json()
n = len(got["items"][0]["datapoints"])
print(n, "readings in the hour")
assert n == 3600, n
```

Several series go in one frame by concatenating their sorted rows in ascending id order and
adding one directory entry each; several frames go in one body back to back, one value type per
frame. Cut a new frame at the [row cap](#caps) for the type.

The same shape in Rust is `arrow_ipc::writer::StreamWriter` over a `RecordBatch` with that schema
(`DataType::Timestamp(TimeUnit::Millisecond, Some("UTC".into()))`, `Decimal128(18, 6)` for a
`numeric` series), the `zstd` crate around its bytes, and the envelope written with
`to_le_bytes`.
