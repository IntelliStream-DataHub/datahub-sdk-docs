---
sidebar_position: 8
title: Subscriptions
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Subscriptions

Durable, fan-out subscriptions over time-series, plus **live delivery over a WebSocket**.

## Manage subscriptions

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
Subscription sub = new Subscription();
sub.setExternalId("engine_temps");
// configure which series the subscription covers
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

## Live delivery

`listen` opens an authenticated WebSocket over one or more subscriptions. Drive it in a
loop and **ack** the messages you've processed — anything left unacked is redelivered on
reconnect.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

The listener is `AutoCloseable`; `poll` returns `null` on timeout:

```java
import ai.intellistream.datahub.sdk.subscriptions.SubscriptionListener;
import ai.intellistream.datahub.sdk.subscriptions.SubscriptionMessage;
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

Every listener also exposes `ack`/`nack`, `subscribe`/`unsubscribe`/`set_subscriptions`
to change the live interest set at runtime, and `close`.

A delivered message carries the originating subscription's external id, an opaque
`messageId` you echo back to `ack`/`nack`, and a `payload` describing the fan-out event
(an action — create/update/delete — plus the affected datapoints).

:::tip Acking is at-least-once
Ack a message only after you've durably handled it. If your process dies before the ack,
the server redelivers it — so make your handler idempotent.
:::
