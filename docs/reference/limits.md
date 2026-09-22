---
sidebar_position: 11
title: Limits & quotas
description: The size, rate and volume ceilings the API enforces, the status code each one answers with, and which of them a client should retry.
---

# Limits & quotas

The API enforces six kinds of ceiling, and the status code says which one you hit and what to
do about it. That is the whole design: **what clears by waiting answers `429` and carries a
`Retry-After`, and what does not answers something else.** Retry the first kind, fix the
second.

| Limit | Status | Problem `type` | How it clears |
| --- | --- | --- | --- |
| [Field caps](#field-caps) | `400` / `422` | the usual validation body | Shorten the field |
| [Batch caps](#batch-caps) | `400` / `422` | the usual validation body | Split the batch |
| [Request body size](#request-body-size) | `413` | `.../errors/request-too-large` | Split the batch |
| [Binary frame caps](#binary-frames) | `400` / `413` | `.../errors/invalid-frame` on the `400`, `.../errors/request-too-large` on the `413` | Split the frame or fix the producer |
| [Rate limit](#rate-limits) | `429` + `Retry-After` | `.../errors/rate-limit-exceeded` | Wait the seconds it names |
| [Daily ingest quota](#daily-ingest-quotas) | `429` + `Retry-After` | `.../errors/ingest-quota-exceeded` | Wait until 00:00 UTC |
| [Lifetime ceiling](#lifetime-ceilings) | `403`, no `Retry-After` | `.../errors/tenant-limit-reached` | Ask for it to be raised |
| [Graph transfer](#graph-transfer) | `400` on export, `413` on import | an `error` body, not a problem document | It does not: the component is too large to move as one file |

Every `type` above is prefixed `https://intellistream.ai/errors/`, and the `429` and `413`
bodies are [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem documents served as
`application/problem+json`. They reach you through the ordinary error path in each client
(`DatahubApiException` in Java, `DataHubException` in Python, `ResponseError` in Rust); see
[Results & errors](./client#results--errors).

:::note The numbers are defaults, not guarantees
Rate limits, quotas, ceilings and WebSocket caps are deployment policy: an operator sets
them, and a tenant can be given its own. [Lifetime ceilings](#lifetime-ceilings) are off
altogether unless a deployment turns them on. Read the `limit` field off the response rather
than hard-coding the value. The field, batch and binary frame caps below are the wire contract
and do not vary.
:::

## Field caps {#field-caps}

Each of these bounds one entity. They apply on **create and on update alike**: the update
forms enforce the same cap on `set` and on `add`, so you cannot grow past a cap one append at
a time.

| Field | Cap |
| --- | --- |
| `description` | 10 000 characters |
| `metadata` | 256 entries, keys 128 characters, values 1 024 characters |
| `labels` | 64 labels, each at most 512 characters |
| `relatedResources` | 100 entries |
| `geoLocation`, as raw GeoJSON | 65 536 characters |
| Datapoint `value` | 64 characters |

`description` is capped everywhere it appears: events, resources, time series, data sets,
policies, functions and relationships.

## Batch caps {#batch-caps}

| Payload | Cap |
| --- | --- |
| `items` in a `DataWrapper` | 10 000 |
| Nodes and relations in `POST /resources/create` and `/resources/update` | 1 000 each |
| `datapoints` in one `DatapointsCollection`, numeric series | 100 000 |
| `datapoints` in one `DatapointsCollection`, `TEXT` or `MIXED` series | 10 000 |

The `items` cap covers every endpoint taking the standard envelope: `/events/create`,
`/events/update`, `/events/delete`, `/timeseries/data`, `/timeseries/create`, `/edges/create`,
`/datasets/create`, `/labels/create`, `/policies/create` and `/functions/create`.

The tighter [`TEXT`/`MIXED`](./timeseries#value-types) cap is checked in the service, once the
series' value type has been resolved, so it comes back naming the series type rather than the
field. Split a text series into collections of 10 000 points or fewer.

The `items` cap is enforced wherever the handler validates the body. `/events/update` and
`/events/delete` do not, so an oversized update or delete batch is bounded only by the
[request body size](#request-body-size).

## Request body size {#request-body-size}

| Endpoint | Cap |
| --- | --- |
| `POST /timeseries/data` | 16 MiB |
| `POST /timeseries/data/binary` | 64 MiB compressed, `datahub.limits.max-body-bytes-datapoints-binary` |
| Everything else | 4 MiB |
| `PUT /files` and `GET /files/download/**` | exempt, they stream |
| `POST /resources/import` and `GET /resources/export/{id}` | exempt, they stream; the [file format](#graph-transfer) has its own ceilings |

```json
{
  "type": "https://intellistream.ai/errors/request-too-large",
  "title": "Request body too large",
  "status": 413,
  "detail": "The request body exceeds the 4194304 byte limit for this endpoint.",
  "limitBytes": 4194304
}
```

A `413` is **terminal**. The same request will never become acceptable by being sent again,
so split the batch instead of retrying it.

`POST /timeseries/data/binary` answers a body over its cap the same way, `request-too-large`
with `limitBytes` and no `reason`, before any frame is read. A body under the cap can still
break a [frame cap](#binary-frames): the same `413` and `type`, plus a `reason`.

## Binary frame caps {#binary-frames}

[`POST /timeseries/data/binary`](./binary-datapoints) carries datapoints as frames, and the
frame format fixes its own caps. Every refusal is a problem document carrying the `type` its
status calls for, `.../errors/invalid-frame` on a `400`, `.../errors/request-too-large` on a
`413` and `.../errors/too-many-in-flight` on the `429`, each with a stable `reason` beside it,
and nothing of the request was inserted:

| Cap | Value | Answered with |
| --- | --- | --- |
| Rows per frame, numeric series | 100 000 | `400`, `row-count-mismatch` |
| Rows per frame, `TEXT` or `MIXED` series | 10 000 | `400`, `row-count-mismatch` |
| Series per frame | 10 000 | `400`, `directory-invalid` |
| Text value | 64 characters and 256 bytes | `400`, `value-invalid` |
| Decompressed payload per frame | 4 MiB | `413`, `frame-too-large` |
| Frames per request | 32 | `413`, `too-many-frames` |
| Decompressed total per request | 64 MiB | `413`, `request-too-large` |
| Binary requests validated at once, per API instance | deployment policy | `429`, `too-many-in-flight`, `Retry-After: 1` |

The `400`s mean the producer is wrong and the `413`s mean split; only the `429` clears by
waiting. The full list of reasons, and the retry rules, are on
[Binary datapoint frames](./binary-datapoints#responses).

## Graph transfer {#graph-transfer}

[Export and import](./resources#graph-transfer) of a graph component have ceilings of their
own, fixed in the file format rather than set by the deployment:

| Limit | Cap | Answered with |
| --- | --- | --- |
| Nodes in one component or file | 2 000 000 | `400` on export, `413` on import |
| Relationships in one component or file | 2 000 000 | `400` on export, `413` on import |
| Compressed file size on import | 512 MB | `413` |

These answer with the `{ "error": { "code", "message" } }` body the resource endpoints use,
not a problem document, and none of them clears by waiting: a component over the cap cannot
be exported as one file at all.

## Rate limits {#rate-limits}

Counted per organization and per user in a fixed one-minute window, with separate budgets for
reads and writes.

Which budget a request spends follows what it **does**, not which method it uses. A `GET` is a
read and a `PUT`, `PATCH` or `DELETE` is a write, but a `POST` that only reads because it
carries a filter body is charged as a read: `/events/filter`, `/resources/search`,
`/timeseries/data/list`, `/timeseries/byids` and every other endpoint whose last path segment
is `filter`, `search`, `byids`, `list`, `count`, `check`, `fetch-related`, `fetch-nearest`,
`aggregate` or `latest`. So a poller sitting on a filter endpoint budgets against the read
allowance, which is the larger of the two.

| Scope | Writes / min | Reads / min |
| --- | --- | --- |
| Organization | 2 000 | 6 000 |
| User | 600 | 1 200 |

```json
{
  "type": "https://intellistream.ai/errors/rate-limit-exceeded",
  "title": "Too many requests",
  "status": 429,
  "detail": "This tenant has used its 2000 requests per minute. Retry in 37 seconds.",
  "scope": "tenant",
  "limit": 2000,
  "retryAfter": 37
}
```

`scope` is `tenant` or `user`, which tells you whether the noisy neighbour is you or your
colleagues. `Retry-After` carries the same seconds as `retryAfter`, and never exceeds the 60
seconds left in the window.

The [MCP tools](/mcp-server) at `/mcp` spend the **same budget** as REST: an agent and your
ingest job share one allowance.

## Daily ingest quotas {#daily-ingest-quotas}

Per organization, per UTC day, reset at 00:00 UTC. `Retry-After` points at that reset, so it
can be hours.

| `metric` | Default per day |
| --- | --- |
| `events` | 100 000 |
| `nodes` | 50 000 |
| `relationships` | 100 000 |
| `data points` | 10 000 000 |
| `ingested bytes` | 1 GiB of write-request body |

`nodes` is the shared count of resources, time series, data sets, labels, policies and
functions: they are one population, not five. On the [binary datapoint path](./binary-datapoints)
`ingested bytes` counts the **decompressed** size of the frames, so compressing harder does not
stretch the allowance, and every quota is charged after validation, so a refused request costs
nothing.

```json
{
  "type": "https://intellistream.ai/errors/ingest-quota-exceeded",
  "title": "Ingest quota exceeded",
  "status": 429,
  "detail": "Daily events ingest quota (100000) is spent; it resets at 00:00 UTC.",
  "metric": "events",
  "limit": 100000,
  "retryAfter": 43200
}
```

## Lifetime ceilings {#lifetime-ceilings}

Totals, not rates: how large an organization may grow. Unlike everything above, these are
**off unless a deployment turns them on**, and the numbers size a free or trial organization.
Handle the `403`, but do not plan your data model around these figures: ask whoever runs your
deployment what applies to you.

| `metric` | Ceiling where they are on |
| --- | --- |
| `objects` (resources, time series, data sets, labels and policies share it) | 1 000 |
| `events` | 25 000 |
| `data points` | 1 000 000 000 |
| `text data points`, on `TEXT` / `MIXED` series | 100 000 |

```json
{
  "type": "https://intellistream.ai/errors/tenant-limit-reached",
  "title": "Tenant limit reached",
  "status": 403,
  "detail": "This tenant has reached its limit of 25000 events. Contact IntelliStream to have it raised.",
  "metric": "events",
  "limit": 25000
}
```

There is deliberately **no `Retry-After`**: waiting does not clear a ceiling, and the status
is `403` rather than `429` so no client mistakes it for one that does. The ceiling moves when
someone raises it, which is a conversation with whoever operates the deployment, not a retry.

Whether deleting helps depends on the metric:

| Metric | Counted | Does deleting free room? |
| --- | --- | --- |
| `objects` | Live rows | **Yes** |
| `events`, `data points` | Cumulative | **No** |

## WebSocket caps {#websockets}

Both endpoints, `/timeseries/datapoints/subscription/listen/**` and
`/timeseries/datapoints/listen`:

| Cap | Default |
| --- | --- |
| Concurrent connections per organization | 10 |
| Concurrent connections per user | 10 |
| Subscriptions multiplexed over one socket | 10 |

**Over the connection cap**, the server sends one error frame naming the limit and then
closes with **1008** (policy violation), so you get a reason instead of a bare close. Both
sockets send the same shape, so one parser reads either:

```json
{"error":true,"reason":"websocket-limit-reached","scope":"tenant","limit":10,"message":"..."}
```

**Over the per-socket subscription cap**, the socket **stays open**: the subscriptions
already attached to it are still valid, and only the one that would not fit is refused.

```json
{"error":true,"subscriptionExternalId":"engine_temps","reason":"subscription-limit-reached"}
```

It arrives on the same path as the other per-subscription refusals
(`forbidden`, `not-found`), so a client that already handles those handles this one. See
[Subscriptions](./subscriptions#live-delivery).

## What the SDKs do about it {#sdk-behaviour}

The split above lines up with what the ingest paths already do, so most of this needs no code
from you:

| Response | Retried in process | Spooled when [buffering](./client#durable-ingest-buffering) is on |
| --- | --- | --- |
| `429` (rate limit, daily quota), `5xx`, network failure | Java: **yes**, with backoff, except a `5xx` the API explains as `needs-operator` (a `500 internal`). Rust and Python: on the binary path, see below | Yes, and Rust and Python send it again on the next ingest call |
| `401`, and `403` on a grant | No | Yes, until the credential is fixed |
| `403` on a [lifetime ceiling](#lifetime-ceilings) | No | Java: **no**, surfaced to you. Rust and Python: **yes**, like any `403` |
| `400` / `422` (validation), `413` (body too large) | No | No, surfaced to you |
| `404 unknown-timeseries` / `422 external-id-mismatch` on the [binary path](./timeseries#binary-ingest) | **Once**, after re-resolving the series | No, the binary path has no spool |

Java's `ingest` reads the `retry` member of the
[problem document](./client#problem-documents) where the answer carries one, and falls back to
the status where it does not (a network failure, a proxy's HTML `502`). It backs off and replays a `429`, a
`502`/`503`/`504`, a network failure and anything else marked `same-request`, up to `maxRetries`
times; a `500` the API marks `needs-operator` is surfaced instead. Its backoff is floored at the
`Retry-After` the response asked for, and a `Retry-After` over 30 seconds fails the batch at once
rather than sleeping, so a spent daily quota reaches your code, or the spool, instead of holding
a thread until 00:00 UTC.

Rust and Python retry JSON ingest through the spool instead: with buffering on, a `429`, `5xx` or
network failure is written to disk and the next ingest call sends it again, oldest first, before
its own data; with it off, the error reaches your code. Their binary
path, `insert_datapoints_binary`, retries `429`, `5xx` and network failures up to three times
by default, 1, 2 and 3 seconds apart. Neither waits the `Retry-After`, so a rate limit that
outlasts those retries, or a daily quota, ends in the spool or in your code the same way.
A `413` or a validation failure reaches your code, which is the right place for it, since
neither is fixed by trying again.

In Java, a lifetime ceiling is the one `403` that does **not** spool: it surfaces on the call
that hit it, in `errors()` on the [`IngestResult`](./timeseries#ingestresult). Why Java treats
it differently from the other `403`s is under
[durable ingest buffering](./client#durable-ingest-buffering). Rust and Python spool it like
any other `403` when buffering is on, so the call returns without an error and the data waits
in the spool until the time window or size cap drops it. With buffering off, the `403` reaches
your code.

Things to check in your own configuration:

- **Java: `batchSize` defaults to `10 000`**, exactly the `items` cap. If you raised it, lower
  it back to 10 000 or below. See [IngestOptions](./timeseries#ingestoptions). Rust and Python
  have no batch size to set: `insert_datapoints` cuts requests at 100 000 datapoints, the
  numeric per-collection cap.
- **A `TEXT` or `MIXED` series batch must stay at or under 10 000 points per collection**,
  whatever `batchSize` says. The Rust and Python chunking does not look at the value type
  either, so split a text series yourself. A numeric batch of 10 000 points is roughly 500 KB
  of JSON, comfortably inside the 16 MiB datapoint body cap.
- **Rust and Python: `DATAPOINT_INSERT_PARALLELISM` sets how many datapoint requests are in
  flight at once**, default `4`. Rust also takes `set_datapoint_insert_parallelism` on
  `DataHubConfig`; Python reads it only from the environment, through `from_env()` or
  `from_envfile(path)`. It applies with buffering off, since the buffered path sends one
  request at a time. Each request can carry 100 000 points that the API holds in memory while
  it parses them, so raise it with care. Java's counterpart is `parallelism` on
  [IngestOptions](./timeseries#ingestoptions).
- **The binary path has no size knob to get wrong**: `ingestBinary` (Java) and
  `insert_datapoints_binary` (Rust, Python) cut frames and requests under the
  [binary frame caps](#binary-frames) themselves. Rust tunes it with `BinaryIngestOptions`:
  `zstd_level` (`9`), `max_retries` (`3`) and `request_concurrency` (`4`). Python takes only
  `zstd_level=`.
