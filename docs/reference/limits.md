---
sidebar_position: 11
title: Limits & quotas
description: The size, rate and volume ceilings the API enforces, the status code each one answers with, and which of them a client should retry.
---

# Limits & quotas

The API enforces a handful of ceilings, and the status code says which one you hit and what to
do about it. That is the whole design: **what clears by waiting answers `429` and carries a
`Retry-After`, and what does not answers something else.** Retry the first kind, fix the
second.

| Limit | Status | Problem `type` | How it clears |
| --- | --- | --- | --- |
| [Field caps](#field-caps) | `400` / `422` | the usual validation body | Shorten the field |
| [Batch caps](#batch-caps) | `400` / `422` | the usual validation body | Split the batch |
| [Request body size](#request-body-size) | `413` | `.../errors/request-too-large` | Split the batch |
| [Rate limit](#rate-limits) | `429` + `Retry-After` | `.../errors/rate-limit-exceeded` | Wait the seconds it names |
| [Daily ingest quota](#daily-ingest-quotas) | `429` + `Retry-After` | `.../errors/ingest-quota-exceeded` | Wait until 00:00 UTC |
| [Lifetime ceiling](#lifetime-ceilings) | `403`, no `Retry-After` | `.../errors/tenant-limit-reached` | Ask for it to be raised |

Every `type` above is prefixed `https://intellistream.ai/errors/`, and the `429` and `413`
bodies are [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem documents served as
`application/problem+json`. They reach you through the ordinary error path in each client
(`DatahubApiException` in Java, `DataHubException` in Python, `ResponseError` in Rust); see
[Results & errors](./client#results--errors).

:::note The numbers are defaults, not guarantees
Rate limits, quotas, ceilings and WebSocket caps are deployment policy: an operator sets
them, and a tenant can be given its own. [Lifetime ceilings](#lifetime-ceilings) are off
altogether unless a deployment turns them on. Read the `limit` field off the response rather
than hard-coding the value. The field and batch caps below are the wire contract and do not
vary.
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

:::caution The OpenAPI schema used to advertise caps nothing enforced
Some endpoints, `/events/delete` among them, carried a documented maximum in the schema that
the runtime never checked, so an oversized batch went through. Those caps are **enforced
now**. Code written against the advertised numbers is unaffected; code that quietly relied on
them not being real is not.
:::

## Request body size {#request-body-size}

| Endpoint | Cap |
| --- | --- |
| `POST /timeseries/data` | 16 MiB |
| Everything else | 4 MiB |
| `PUT /files` and `GET /files/download/**` | exempt, they stream |

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

## Rate limits {#rate-limits}

Counted per organisation and per user in a fixed one-minute window, with separate budgets for
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
| Organisation | 2 000 | 6 000 |
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

Per organisation, per UTC day, reset at 00:00 UTC. `Retry-After` points at that reset, so it
can be hours.

| `metric` | Default per day |
| --- | --- |
| `events` | 100 000 |
| `nodes` | 50 000 |
| `relationships` | 100 000 |
| `data points` | 10 000 000 |
| `ingested bytes` | 1 GiB of write-request body |

`nodes` is the shared count of resources, time series, data sets, labels, policies and
functions: they are one population, not five.

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

Totals, not rates: how large an organisation may grow. Unlike everything above, these are
**off unless a deployment turns them on**, and the numbers size a free or trial organisation.
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
someone raises it, which is a conversation with IntelliStream, not a retry.

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
| Concurrent connections per organisation | 10 |
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
| `429` (rate limit, daily quota), `5xx`, network failure | **Yes**, with backoff | Yes |
| `401`, and `403` on a grant | No | Yes, until the credential is fixed |
| `403` on a [lifetime ceiling](#lifetime-ceilings) | No | **No**, surfaced to you |
| `400` / `422` (validation), `413` (body too large) | No | No, surfaced to you |

So rate limits and daily quotas take care of themselves: the client backs off and replays.
A `413` or a validation failure reaches your code, which is the right place for it, since
neither is fixed by trying again.

A lifetime ceiling is the one `403` that does **not** spool. The others are worth spooling
because an expired token or a missing grant is fixed out of band and the data then flushes; a
ceiling never becomes acceptable by being replayed, so buffering it would fill the spool with
data the server refuses every time and bury the one message that says the limit is raised by
asking. The client tells them apart on the problem `type`, so the ceiling surfaces on the call
that hit it, in `errors()` on the [`IngestResult`](./timeseries#ingestresult).

Two things to check in your own configuration:

- **`batchSize` defaults to `10 000`**, exactly the `items` cap. If you raised it, lower it
  back to 10 000 or below. See [IngestOptions](./timeseries#ingestoptions).
- **A `TEXT` or `MIXED` series batch must stay at or under 10 000 points per collection**,
  whatever `batchSize` says. A numeric batch of 10 000 points is roughly 500 KB of JSON,
  comfortably inside the 16 MiB datapoint body cap.
