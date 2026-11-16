---
sidebar_position: 4.5
title: Binary datapoint frames
description: The wire format of POST /timeseries/data/binary and POST /timeseries/data/list/binary, the high-throughput datapoint insert and read, for anyone producing or reading frames outside the SDKs.
---

# Binary datapoint frames

`POST /timeseries/data/binary` is the high-throughput form of
[`POST /timeseries/data`](./timeseries#write-datapoints). The body is one or more
**datapoint frames**: a 28-byte envelope, a directory of the series in the frame, and an Arrow
IPC stream in one canonical schema per value type, zstd-compressed whole or buffer by buffer,
rows sorted by series and timestamp. Nothing is parsed as text, so a request carries up to a
million points in a few megabytes. [`POST /timeseries/data/list/binary`](#reading) answers a
read in the same frames, and its answer is a valid body to post back.

The SDKs build frames for you, see [binary ingest](./timeseries#binary-ingest): `ingestBinary` in
Java, `insert_datapoints_binary` in Rust and in Python's synchronous client. This page is the
byte-level contract for everyone else: a producer with pyarrow or arrow-rs, or a gateway
forwarding frames it did not build. Java reads them with `retrieveBinary`, see
[binary read](./timeseries#binary-read).

| | |
| --- | --- |
| Method and path | `POST /timeseries/data/binary` |
| `Content-Type` | `application/vnd.intellistream.datapoint-block` |
| `Content-Encoding` | None (or `identity`). Compression lives inside each frame; any other body-level encoding is a `415`. |
| Body | One or more frames back to back, the last ending exactly at the end of the body, or followed by a read's `DHDE` end marker, so a read's answer posts back as it is. |
| Success | `204`, no body. Every frame in the request was validated and published. |
| Failure | An [`application/problem+json`](#responses) document, and **nothing** was inserted. |

## The envelope {#envelope}

All integers are little-endian.

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | Magic, the ASCII bytes `DHDP`. |
| 4 | 1 | Version, `1`. |
| 5 | 1 | Value type id: `1` bigint, `2` float, `3` numeric, `4` text, `5` decimal32, `6` mixed, `7` float32. |
| 6 | 1 | Codec, `1` = Arrow IPC stream. `2` = Arrow IPC stream of [aggregates](#aggregate-schema), sent by reads only; ingest refuses it with `unsupported-codec`. `0` is reserved. |
| 7 | 1 | Compression: `1` = zstd on the whole payload, `2` = zstd on each Arrow buffer in-band, see [the payload](#payload). Required: `0` is refused with `uncompressed-frame`. |
| 8 | 4 | `u32` row count, at least 1. |
| 12 | 4 | `u32` series count, the number of distinct series ids in the payload. |
| 16 | 4 | `u32` directory length in bytes. |
| 20 | 4 | `u32` payload length in bytes, as carried (compressed). |
| 24 | 4 | `u32` decompressed length in bytes: at compression `1` the whole payload, at `2` the record batch bodies with every buffer uncompressed. |
| 28 | | The [directory](#directory), then the [payload](#payload). |

The zstd level is the sender's choice. The API decompresses into exactly the declared number of
bytes, and a stream or a buffer that ends early or runs long is refused.

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

One Arrow IPC **stream**: one schema message, one or more record batches, and the end-of-stream
marker, with nothing after it. Little-endian throughout. It is compressed one of two ways, the
envelope's byte 7 saying which:

- **Compression `1`**: the whole stream is one zstd frame, and the record batches inside carry
  their buffers uncompressed. What the Rust and Python SDKs send.
- **Compression `2`**: the stream is carried as it is, and every record batch compresses its
  buffers in-band, Arrow's body compression with codec `ZSTD` and method `BUFFER`. Each
  non-empty buffer is then its uncompressed length as an `int64`, followed by the zstd stream,
  or `-1` followed by the bytes as they are; an empty buffer stays empty. The envelope's
  decompressed length is the bodies' total with every buffer uncompressed, each padded to 8
  bytes. This is what pyarrow writes with `IpcWriteOptions(compression="zstd")` and reads
  without being told, what arrow-rs reads with its `zstd` feature, what a
  [read](#reading) answers with, relayed from the database as it compressed them, and what the
  Java SDK sends.

The stream is read by a minimal codec that accepts exactly the subset a plain writer emits and
refuses the rest, with the `reason` on the right:

| Rule | `reason` |
| --- | --- |
| Every message uses the continuation-marker framing (`0xFFFFFFFF`, then the metadata length), metadata version V4 or newer. | `payload-invalid` |
| Exactly one schema message, before any record batch, with no body. | `payload-invalid` |
| The schema matches the [canon](#schemas) for the frame's value type: field count, names, types with their parameters, nullability; no dictionary encoding, no children. Custom metadata is ignored. | `schema-mismatch` |
| No dictionary batches; no variadic buffers. Record batch bodies are compressed in-band at compression `2`, every batch, with zstd by buffer, and not at `1`. | `payload-invalid` |
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

### Aggregate frames {#aggregate-schema}

A read item with `aggregates` and a `granularity` is answered with codec `2`. The value type byte
is still the series' type, but the schema is the same for every type, all fields non-nullable:

| Field | Arrow type | Meaning |
| --- | --- | --- |
| `timeseries_id` | `Int64` | The series. |
| `timestamp` | `Timestamp(MILLISECOND, "UTC")` | The bucket start. |
| `avg` | `Float64` | Time-weighted average. |
| `min`, `max`, `sum` | `Float64` | In that order. |

All four aggregates are present whatever `aggregates` named. There is one row per bucket that
holds a point. A `text` series has no aggregates (`400`), and a `mixed` series aggregates its
numeric values only.

## Caps {#caps}

Fixed in the format, not deployment policy, except the last row:

| Cap | Value | Over it |
| --- | --- | --- |
| Rows per frame, numeric types | 100 000 | `400 row-count-mismatch` |
| Rows per frame, `text` or `mixed` | 10 000 | `400 row-count-mismatch` |
| Rows per aggregate frame (reads only) | 50 000 | |
| Series per frame | 10 000 | `400 directory-invalid` |
| External id in the directory | 1 024 bytes | `400 directory-invalid` |
| Text value | 64 characters and 256 bytes | `400 value-invalid` |
| Decompressed payload per frame | 4 MiB | `413 frame-too-large` |
| Frames per request | 32 | `413 too-many-frames` |
| Decompressed total per request | 64 MiB | `413 request-too-large` |
| Compressed body per request | 64 MiB by default, `datahub.limits.max-body-bytes-datapoints-binary` | `413`, no `reason` |

A frame is published as one message, so the 4 MiB keeps it under the broker's limit with room
to spare. 100 000 float points are about 2.4 MB decompressed and a few hundred KB compressed, so
a full frame is comfortably inside it; a producer only needs to split on the row cap.

A [read](#reading) answers in frames within the same per-frame caps, but the request caps (32
frames, 64 MiB) do not apply to its response. To post an answer back, split it at frame
boundaries so each request stays under them.

## Responses {#responses}

Every refusal is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem document carrying
the `type` its status calls for, with a stable `reason` beside it as the sub-code, plus
`frameIndex` (0-based) when one frame is at fault and `timeseriesIds` when particular series are.
Branch on the `type`, and on `reason` to tell apart the thirteen ways a frame can be malformed:

```json
{
  "type": "https://intellistream.ai/errors/external-id-mismatch",
  "title": "External id mismatch",
  "status": 422,
  "detail": "2 series in frame 3 have a different external id than the directory says; refresh the client's series cache.",
  "reason": "external-id-mismatch",
  "frameIndex": 3,
  "timeseriesIds": [1041, 1042]
}
```

Every `type` below is prefixed `https://intellistream.ai/errors/`.
| Status | `type` | `reason` | Meaning |
| --- | --- | --- | --- |
| `204` | | | Accepted and published. |
| `400` | `invalid-frame` | `malformed-frame`, `unsupported-version`, `unsupported-codec`, `unknown-value-type`, `uncompressed-frame`, `trailing-bytes`, `directory-invalid`, `payload-invalid`, `schema-mismatch`, `row-count-mismatch`, `unsorted`, `duplicate-row`, `value-invalid` | The frame at `frameIndex` breaks the format; `detail` says where. Fix the producer. |
| `403` | `dataset-forbidden`, or `tenant-limit-reached` | | The caller lacks write on a series' data set (the usual [data set `403`](./datasets#access-control)), or the tenant is at a [lifetime ceiling](./limits#lifetime-ceilings). Neither carries a `reason`. |
| `404` | `unknown-timeseries` | `unknown-timeseries` | `timeseriesIds` do not exist in this tenant. Re-resolve them. |
| `413` | `request-too-large` | `frame-too-large`, `too-many-frames`, `request-too-large` | Over a [cap](#caps). Split; a retry as-is never succeeds. A body over the compressed cap is refused before any frame is read, without a `reason`. |
| `415` | `unsupported-media-type` | `unsupported-content-encoding` | A `Content-Encoding` header. The wrong `Content-Type` is also a `415`, from the framework, without a `reason`. |
| `422` | `value-type-mismatch` | `value-type-mismatch` | `timeseriesIds` in `frameIndex` have another value type than the envelope declares. |
| `422` | `external-id-mismatch` | `external-id-mismatch` | `timeseriesIds` in `frameIndex` have another external id than the directory says. Drop them from your cache and resolve again. |
| `429` | `too-many-in-flight` | `too-many-in-flight` | This API instance is already validating its limit of binary requests; `Retry-After` is one second and [`retry`](./client#problem-documents) is `same-request`. |
| `429` | `rate-limit-exceeded`, `ingest-quota-exceeded` | | The ordinary [rate limit](./limits#rate-limits) or [daily quota](./limits#daily-ingest-quotas), with no `reason`. |

Two of the seven binary types are the API's own rather than this endpoint's: an oversized request
is `request-too-large` and a rejected `Content-Encoding` is `unsupported-media-type` whichever
path produced it, so a client that already handles them needs nothing new here. The other five
are specific to binary frames.

All seven used to be one type, `datapoint-block-rejected`, which therefore answered `400`, `404`,
`413`, `415`, `422` and `429`; RFC 9457 gives a type one status. A client matching on that type
matches nothing now. `reason` is unchanged, so one matching on `reason` still works.

### Retrying {#retrying}

Every frame is validated before any is published, so a rejected request inserted **nothing** and
is retried **as a whole**. Datapoints are keyed by `(series, timestamp)`, so replaying a request
that did reach the store, say after a lost response, is harmless.

- `429` with `Retry-After`, a `502`/`503`/`504` and a dropped connection: wait and resend the same
  body. The document says so itself in `retry`, and a refusal marked `needs-operator` (a `500`,
  say) is not worth resending.
- `404 unknown-timeseries` and `422 external-id-mismatch`: forget the named ids, look them up
  again by external id, rebuild the frames and resend once. If it fails the same way, the series
  really is gone.
- Everything else: fix the request.

The Java and Rust SDKs handle the first two for you, and Python's binary methods do through
Rust. Rust waits a second longer before each retry rather than reading `Retry-After`.

Quotas are charged after validation, so a refused request costs nothing. The
[`ingested bytes`](./limits#daily-ingest-quotas) quota counts **decompressed** bytes on this
path: compressing harder does not stretch the allowance.

## Reading frames {#reading}

`POST /timeseries/data/list/binary` takes the same JSON body as
[`POST /timeseries/data/list`](./timeseries#retrieve-datapoints) and answers in frames.

| | |
| --- | --- |
| Method and path | `POST /timeseries/data/list/binary` |
| `Content-Type` | `application/json`: a `DataRetriever` of `RetrieveFilter` items, each with `start` or `end` |
| `Accept` | `application/vnd.intellistream.datapoint-block, application/problem+json`, so a refusal comes back as a problem document |
| Success | `200`, `application/vnd.intellistream.datapoint-block`: zero or more frames back to back, at compression `2`, then the 4-byte end marker, the ASCII bytes `DHDE`. Nothing follows the marker. |
| Failure | Before the first byte: a `400` problem document (invalid filter, items' limits over the request's `limit`, a `cursor`, aggregates of a `text` series, or a series that is unknown or unreadable unless `ignoreUnknownIds` is set), or a `500` on a server failure. After that, the body just ends early. |

**A body without `DHDE` was cut short**, inside a frame or between two, and is an error, not a
shorter answer. The request is a read, so send it again.

- Frames come in the order of `items`, and one series' rows may span several consecutive frames.
  The server currently puts one series in each frame; read the [directory](#directory) rather than
  relying on it.
- The frames carry the Arrow record batches as the database compressed them, each buffer zstd
  in-band (compression `2`), relayed without being decoded on the way; the reader decompresses.
  A frame holds as many whole batches as fit under its row cap, so most hold fewer rows than
  the cap: never expect full frames.
- The answer, end marker included, is a valid body for `POST /timeseries/data/binary` as long
  as it holds no aggregate frame and stays under the request caps, split at frame boundaries if
  not. Java's `ingestFrames` does that.
- A series with no points in its window sends no frame, so a body of `DHDE` alone is valid.
- Rows are sorted by timestamp, oldest first, and each item returns at most its `limit` from
  `start`, or every point in its window when it has none. A point sent twice is read once.
- Values come in [value frames](#schemas) (codec `1`, the series' canonical schema, as on ingest);
  an item with `aggregates` and a `granularity` in [aggregate frames](#aggregate-schema) (codec `2`).
- There is no cursor, and a `cursor` in an item is a `400`. To read on, send the request again with
  `start` one millisecond past the last timestamp you got.

| Read limit | Value |
| --- | --- |
| Rows per request | None. An item without a `limit` returns every point in its window, streamed as it is read, so bound a long series with `end` |
| An item's `limit` | At most 100 000, the retrieve body's own ceiling; leave it out, or send `null`, to read more of one series |
| The request's top-level `limit`, if given | The request's total: items' limits adding up to more is a `400`, and the items without one share what is left |
| Rows per frame | At most 100 000 numeric, 10 000 `text` or `mixed`, 50 000 aggregate; whole database blocks, so usually fewer |

## Producing frames from pyarrow {#pyarrow}

:::info Needs a sandbox
The example writes into `engine_temperature`, which section **A** of
[Seed a sandbox](/guides/seed-a-sandbox) creates.
:::

An IPC stream written by pyarrow or arrow-rs with the schema above and no dictionary encoding is
exactly what the codec accepts. What is left is the envelope and the zstd wrap, or compression
`2` with pyarrow's `IpcWriteOptions(compression="zstd")` and no wrap. The example takes the
first way: it resolves the series, picks the schema its value type calls for, writes an hour of
readings and reads them back:

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
with ipc.new_stream(sink, schema) as writer:          # default options: no in-band compression, so compression 1
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

In Rust you need not write any of this by hand. The SDK exports the pieces its own
`insert_datapoints_binary` uses: `DatapointValueType::schema()` returns the canon for a type,
`ResolvedSeries` is a series' id, external id and value type, and `FrameWriter` sorts,
de-duplicates, compresses and wraps one frame:

```rust
use intellistream_datahub_sdk::timeseries::{DatapointValueType, FrameWriter};

let mut writer = FrameWriter::new(DatapointValueType::Float);
writer.series(id, "engine_temperature")?;          // the id /timeseries/byids returned
for (timestamp_ms, value) in rows {
    writer.add_float(id, timestamp_ms, value)?;
}
let body: Vec<u8> = writer.build(9)?.bytes;        // zstd level; one frame, ready to POST
```

`build` refuses a frame over the [caps](#caps). Check `is_full_for(id)` before each `add` and
start a new writer when it says so; frames go in one body back to back.

## Reading frames with pyarrow {#pyarrow-read}

This reads back the hour the example above wrote, frame by frame, and checks the end marker.
The read answers at compression `2`, which pyarrow undoes by itself; the outer zstd step is for
frames from elsewhere:

```python
import struct
import pyarrow.ipc as ipc, requests, zstandard

r = requests.post(f"{BASE}/timeseries/data/list/binary", headers={
        **HEADERS, "Accept": "application/vnd.intellistream.datapoint-block, application/problem+json"},
    json={"items": [{"externalId": "engine_temperature", "start": t0,
                     "end": t0 + rows * 1000, "limit": 10_000}]})
assert r.status_code == 200, r.text
body, pos, total = r.content, 0, 0
while body[pos:pos + 4] != b"DHDE":
    if pos + 28 > len(body):
        raise IOError("response cut short; send the request again")
    magic, version, type_id, codec, compression, n_rows, n_series, dir_len, pay_len, raw_len = \
        struct.unpack_from("<4sBBBBIIIII", body, pos)
    if pos + 28 + dir_len + pay_len > len(body):
        raise IOError("response cut short; send the request again")
    payload = body[pos + 28 + dir_len : pos + 28 + dir_len + pay_len]
    if compression == 1:                       # the whole stream zstd-wrapped
        payload = zstandard.ZstdDecompressor().decompress(payload, max_output_size=raw_len)
    table = ipc.open_stream(payload).read_all()   # compression 2: the buffers decompress in pyarrow
    total += table.num_rows                    # codec 1: timeseries_id, timestamp, value
    pos += 28 + dir_len + pay_len
assert pos + 4 == len(body), "bytes after the end marker"
print(total, "readings in the hour")
assert total == 3600, total
```
