---
sidebar_position: 9
title: Subscriptions
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Subscriptions

Durable, fan-out subscriptions over time series, plus **live delivery over a WebSocket**.

## Manage subscriptions

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
Subscription sub = new Subscription();
sub.setExternalId("engine_temps");
sub.setName("Engine temps");
sub.setTimeseries(List.of(IdCollection.createFromExternalId("engine_temperature")));
client.subscriptions().create(List.of(sub));

DataWrapper<Subscription> all = client.subscriptions().filter(new SubscriptionRetriever());

client.subscriptions().delete(List.of(IdCollection.createFromExternalId("engine_temps")));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import intellistream_datahub_sdk

sub = intellistream_datahub_sdk.Subscription(
    external_id="engine_temps",
    name="Engine temps",
    timeseries=["engine_temperature"])
client.subscriptions.create([sub])

all_subs = client.subscriptions.filter()

client.subscriptions.delete(["engine_temps"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::subscriptions::{Subscription, SubscriptionFilterForm};
use intellistream_datahub_sdk::generic::IdAndExtId;

let sub = Subscription::new(
    "engine_temps".into(), "Engine temps".into(),
    vec![IdAndExtId::from_external_id("engine_temperature")]);
api.subscriptions.create(&sub).await?;

let all = api.subscriptions.filter(&SubscriptionFilterForm::default()).await?;

api.subscriptions.delete(&vec![IdAndExtId::from_external_id("engine_temps")]).await?;
```

</TabItem>
</Tabs>

:::note Data set access control
Creating a subscription requires **read access to every bound series' data set**. If you
lack read access to any of them, `create` fails with **HTTP 403** and nothing is persisted.
Access is granted through Keycloak **organization groups**: `/datasets/<externalId>/read` for one
data set (and everything beneath it), or the wildcard `/datasets/*/read` for all of them.
[Data set access control →](./datasets#access-control)
:::

## Find subscriptions {#find}

`GET /subscriptions?limit=` returns the newest `limit` subscriptions your token may read, no
body required and no cursor. For anything narrower, or to page, `filter` posts
`POST /subscriptions/filter`, the same envelope every other collection's filter takes, with
criteria combined by **AND**:

| Criterion | Matching |
| --- | --- |
| `id`, `externalId`, `name` | Patterns, case-insensitive. `*` and `%` are wildcards, `_` is literal, and an entry with no wildcard matches exactly. |
| `timeseries` | Subscriptions bound to **any** of these time-series, each named by `id`, `externalId`, or both. |
| `createdTime`, `lastUpdatedTime` | `{ "min": …, "max": … }` bounds. |

Each field above except `createdTime` and `lastUpdatedTime` takes **either a bare value or an
array**, and the entries of an array are combined with **OR**, exactly as on the other
collections' filters.

Both endpoints return only subscriptions you can read in full: every timeseries a subscription
binds must sit in a data set you have read access to, the same rule `create` above and
[live delivery](#live-delivery) enforce. One ungranted timeseries hides the whole subscription.

The page can be ordered and walked exactly as [timeseries](./timeseries#sorting-and-paging)
can: `sort` takes `id`, `externalId`, `name`, `createdTime` or `lastUpdatedTime`, and the
response carries `nextCursor` while more remain.

```json
{
  "limit": 100,
  "filter": {
    "externalId": ["engine_*"],
    "timeseries": [{ "externalId": "engine_temperature" }]
  },
  "sort": { "property": ["createdTime"], "order": "asc" }
}
```

The clients do not all send the whole body yet:

| | Java | Python and Rust |
| --- | --- | --- |
| Criteria | all of them, on `SubscriptionRetriever` | `timeseries` only |
| `cursor` | sent | not sent yet |
| `limit` you did not set | the server's default, 1000 | 100 |

`limit` is capped at 10 000 everywhere. To narrow by series in Python, pass keywords,
`client.subscriptions.filter(timeseries=["engine_temperature"], limit=100)`, or a prepared
`SubscriptionFilterForm`, which is the only form Rust takes.

This replaced `POST /subscriptions/list`, which took a `filter` argument in a shape nothing else
in the API used: its own default page size, a sort that was not validated, and no cursor, so a
tenant past the first page could not reach the rest.

## Live delivery

`listen` opens a WebSocket to `/timeseries/datapoints/subscription/listen/<externalId>/...`,
one path segment per subscription, and authenticates the upgrade request with the same
`Authorization: Bearer <jwt>` header as any REST call. Stream messages to a handler or drive
a loop, and **ack** the messages you've processed, anything left unacked is redelivered on
reconnect.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

`stream` delivers each message on a dedicated virtual thread and auto-acks once the
handler returns (throw to nack); the returned handle is `AutoCloseable`:

```java
import ai.intellistream.datahub.sdk.subscriptions.SubscriptionMessage;

try (var stream = client.subscriptions().listen(List.of("engine_temps"))
        .stream((SubscriptionMessage msg) -> process(msg.payload()))) {
    awaitShutdown();
}
```

Or drive `poll` yourself, a blocking queue hand-off (not network polling) that returns
`null` on timeout. Reach for `poll`, or `stream(handler, AckMode.MANUAL)`, when you need
to ack on your own schedule:

```java
import ai.intellistream.datahub.sdk.subscriptions.SubscriptionListener;
import java.time.Duration;

try (SubscriptionListener listener = client.subscriptions().listen(List.of("engine_temps"))) {
    while (running) {
        SubscriptionMessage msg = listener.poll(Duration.ofSeconds(5));
        if (msg == null) continue;
        process(msg.payload());
        listener.ack(msg.messageId());
    }
}
```

</TabItem>
<TabItem value="python" label="Python">

The listener is iterable and a context manager:

```python
with client.subscriptions.listen(["engine_temps"]) as listener:
    for msg in listener:
        process(msg.payload)
        listener.ack([msg.message_id])
```

</TabItem>
<TabItem value="rust" label="Rust">

`next().await` yields `Some(Ok(msg))`, `Some(Err(..))`, or `None` when the socket closes
(reconnects are transparent):

```rust
let mut listener = api.subscriptions.listen(&["engine_temps"]).await?;
while let Some(result) = listener.next().await {
    match result {
        Ok(msg) => {
            process(&msg.payload);
            listener.ack(&[msg.message_id.as_str()]).await?;
        }
        Err(e) => eprintln!("listen error: {}", e),
    }
}
```

</TabItem>
</Tabs>

Every listener also exposes `stream` for push delivery, `ack`/`nack`,
`subscribe`/`unsubscribe`/`set_subscriptions` to change the live interest set at runtime,
and `close`.

A frame on the wire carries one subscription's messages:

| Field | Type | |
| --- | --- | --- |
| `subscriptionExternalId` | string | The subscription the batch came from. |
| `messages[].messageId` | string | Opaque. Echo it back in an ack or nack. |
| `messages[].payload.eventAction` | `CREATE`, `UPDATE`, `DELETE` or `RENAME` | What happened. |
| `messages[].payload.eventObject` | `DATAPOINTS` | What it happened to. |
| `messages[].payload.items[]` | object[] | One entry per series: `id` (a JSON string), `externalId`, `valueType`, `datapoints[]`, and optionally `inclusiveBegin` and `exclusiveEnd`. |
| `messages[].payload.items[].datapoints[]` | `{ timestamp, value }` | `timestamp` is an ISO-8601 UTC string (`2026-08-30T22:00:00Z`); `value` is a string. |

Ack and nack are `{"action": "ack", "messageIds": [...]}` and the same with `"nack"`. The
clients unpack each entry of `messages` into one message, whose `payload` is the object above.

:::note Refused subscriptions surface as errors
Live delivery enforces the same data set ACL: to attach a subscription you must be able to read
**all** of its bound series. A subscription you can't read (`reason: "forbidden"`) or one that
doesn't exist (`reason: "not-found"`) is refused per-subscription, the connection stays open for
the subscriptions that did attach. The refusal is surfaced, not swallowed: a `SubscriptionError`
via `pollError` in Java, an `Err(ListenError::Subscription { .. })` from `next().await` in Rust, and
an exception raised from the iterator in Python. A refused subscription is therefore visible
instead of looking like an indefinitely silent stream.
:::

:::note Sockets and subscriptions are capped
Ten concurrent connections per organization, ten per user, and ten subscriptions multiplexed
over one socket, by default. The two refusals behave differently, on purpose:

| Over the cap on | The server | The socket |
| --- | --- | --- |
| Connections | Sends `reason: "websocket-limit-reached"`, then closes with **1008** | Closed |
| Subscriptions on one socket | Sends `reason: "subscription-limit-reached"` for the one that did not fit | **Stays open** |

The second arrives on the same per-subscription error path as `forbidden` and `not-found`
above, so a client that handles those handles it. Frame shapes and the configurable numbers
are in [Limits & quotas](./limits#websockets).
:::

:::tip Acking is at-least-once
Ack a message only after you've durably handled it. If your process dies before the ack,
the server redelivers it, so make your handler idempotent.
:::

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Create | `subscriptions().create` | `subscriptions.create` | `subscriptions.create` |
| List (`GET /subscriptions`) | `subscriptions().list` | HTTP | HTTP |
| Filter | `subscriptions().filter` | `subscriptions.filter` | `subscriptions.filter` |
| Delete | `subscriptions().delete` | `subscriptions.delete` | `subscriptions.delete` |
| Live delivery | `subscriptions().listen` | `subscriptions.listen` | `subscriptions.listen` |
