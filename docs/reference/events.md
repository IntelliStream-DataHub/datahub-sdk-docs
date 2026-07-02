---
sidebar_position: 5
title: Events
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Events

Record and query operational events.

## Create

Every event must carry an **event time** — the moment it occurred at the source (sensor,
PLC, upstream system). The SDK deliberately does *not* default it to "now": an event
without it is rejected rather than silently mis-timestamped.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventModel event = new EventModel();
event.setExternalId("door_open");
event.setType("alarm");
event.setEventTime(ZonedDateTime.now());   // required: when the event occurred

client.events().create(List.of(event));
```

</TabItem>
<TabItem value="python" label="Python">

```python
from datetime import datetime, timezone
import datahub_sdk

event = datahub_sdk.Event(
    external_id="door_open",
    type="alarm",
    event_time=datetime.now(timezone.utc))  # required: when the event occurred

client.events.create([event])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use chrono::Utc;
use dataplatform_rust_sdk::events::Event;

let mut event = Event::new("door_open".into());
event.r#type = Some("alarm".into());
event.set_event_time(Utc::now());          // required: when the event occurred
api.events.create(&vec![event]).await?;
```

</TabItem>
</Tabs>

:::note Event ids are time-ordered UUID v7
The ingestion paths stamp every event that has no `id` with a **UUID v7** before sending —
`create` in the Python and Rust clients, `ingest(...)` in Java (a plain Java `create` sends
events as-is and lets the server assign ids). The server honors a client-supplied id, which is
what makes retries idempotent: the events table is a `ReplacingMergeTree` ordered by `id`, so
re-sending the same event (for example after a
[buffered](./client#durable-ingest-buffering) outage) collapses to one row instead of
duplicating. If you set the `id` yourself, use a time-ordered UUID v7 — a random v4 scatters
writes across that sort key and hurts insert/query performance. The created event (with its
id) is returned from `create`.
:::

## Query

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventRetreiver retriever = new EventRetreiver();
retriever.setLimit(50);
retriever.getFilter().setType("alarm");
DataWrapper<EventModel> events = client.events().filter(retriever);
```

</TabItem>
<TabItem value="python" label="Python">

```python
filter = datahub_sdk.EventFilter(
    basic_filter=datahub_sdk.BasicEventFilter(type="alarm"),
    limit=50)
events = client.events.filter(filter)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::filters::{BasicEventFilter, EventFilter};

let filter = EventFilter::default()
    .set_filter(BasicEventFilter { r#type: Some("alarm".into()), ..Default::default() })
    .set_limit(50)
    .build();
let events = api.events.filter(&filter).await?;
```

</TabItem>
</Tabs>

## High-throughput ingestion

<Tabs groupId="lang">
<TabItem value="java" label="Java">

`ingest` chunks, parallelises and retries events the same way as datapoints, returning
the same [`IngestResult`](./timeseries.md#ingestresult) tuned with the same
[`IngestOptions`](./timeseries.md#ingestoptions):

```java
IngestResult result = client.events().ingest(events,
        IngestOptions.builder().batchSize(1_000).parallelism(8).build());
```

</TabItem>
<TabItem value="python" label="Python">

`create` accepts a whole batch:

```python
client.events.create(events)   # list[Event]
```

</TabItem>
<TabItem value="rust" label="Rust">

`create` accepts a whole batch:

```rust
api.events.create(&events).await?;   // Vec<Event>
```

</TabItem>
</Tabs>

## Delete

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
client.events().delete(List.of(IdCollection.createFromExternalId("door_open")));
```

</TabItem>
<TabItem value="python" label="Python">

```python
client.events.delete(["door_open"])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
api.events.delete(&vec![IdAndExtId::from_external_id("door_open")]).await?;
```

</TabItem>
</Tabs>
