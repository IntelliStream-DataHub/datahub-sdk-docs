---
sidebar_position: 8
title: Subscriptions
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Subscriptions

Durable, fan-out subscriptions over time-series, plus **live delivery over a WebSocket**.

## Subscription fields

| Field | Type | Meaning |
| --- | --- | --- |
| `externalId` | string | **Required.** Stable snake_case id, 3–256 chars. Also the Pulsar subscription name. |
| `name` | string | **Required.** Display name, 3–256 chars. |
| `timeseries` | list&lt;IdCollection&gt; | **Required, at least one.** The bound series — see [`IdCollection`](./filters.md#idcollection). |
| `id` | integer | Server-assigned. |
| `systemManaged` | boolean | True when auto-provisioned by function binding. |
| `dateCreated` / `lastUpdated` | timestamp | Server-assigned. |

`create` rejects an empty binding with **HTTP 400**, and every referenced series must
exist. An existing subscription can still end up empty — detaching the last series from a
system-managed one leaves the row in place by design.

## Manage subscriptions

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
Subscription sub = new Subscription();
sub.setExternalId("engine_temps");
sub.setName("Engine temps");
sub.setTimeseries(List.of(IdCollection.createFromExternalId("engine_temperature")));
client.subscriptions().create(List.of(sub));

DataWrapper<Subscription> all = client.subscriptions().list(new SubscriptionRetriever());

client.subscriptions().delete(List.of(IdCollection.createFromExternalId("engine_temps")));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import datahub_sdk

sub = datahub_sdk.Subscription(
    external_id="engine_temps",
    name="Engine temps",
    timeseries=["engine_temperature"])
client.subscriptions.create([sub])

all_subs = client.subscriptions.list()

client.subscriptions.delete(["engine_temps"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::subscriptions::{Subscription, SubscriptionRetriever};
use dataplatform_rust_sdk::generic::IdAndExtId;

let sub = Subscription::new(
    "engine_temps".into(), "Engine temps".into(),
    vec![IdAndExtId::from_external_id("engine_temperature")]);
api.subscriptions.create(&sub).await?;

let all = api.subscriptions.list(&SubscriptionRetriever::default()).await?;

api.subscriptions.delete(&vec![IdAndExtId::from_external_id("engine_temps")]).await?;
```

</TabItem>
</Tabs>

:::note Dataset access control
Creating a subscription requires **read access to every timeseries' dataset** it binds. If your
token lacks a dataset read role for any of them, `create` fails with **HTTP 403** and nothing is
persisted. Access is granted through the Keycloak `DATAHUB_DATASET_READ_*` (or `DATASET_ALL`) realm
roles.
:::

## Live delivery

`listen` opens an authenticated WebSocket over one or more subscriptions. Stream messages
to a handler or drive a loop, and **ack** the messages you've processed — anything left
unacked is redelivered on reconnect.

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

Or drive `poll` yourself — a blocking queue hand-off (not network polling) that returns
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
and `close`. A message carries the originating subscription's external id, an opaque
`messageId` you echo back to `ack`/`nack`, and a `payload` (an action —
create/update/delete — plus the affected datapoints).

:::note Refused subscriptions surface as errors
Attaching requires read access to **all** of a subscription's bound timeseries. A subscription you
can't read (`reason: "forbidden"`) or that doesn't exist (`reason: "not-found"`) is refused
per-subscription — the connection stays open for those that did attach. Refusals surface rather than
producing a silently empty stream: `SubscriptionError` via `pollError` in Java,
`Err(ListenError::Subscription { .. })` from `next().await` in Rust, an exception from the iterator
in Python.
:::

:::tip Acking is at-least-once
Ack a message only after you've durably handled it. If your process dies before the ack,
the server redelivers it — so make your handler idempotent.
:::
