---
sidebar_position: 5
title: Events
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Events

Record and query operational events.

## Create

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
import java.time.ZonedDateTime;

EventModel event = new EventModel();
event.setExternalId("door_open");
event.setEventTime(ZonedDateTime.now());   // also accepts an epoch-millis Long

client.events().create(List.of(event));
```

</TabItem>
<TabItem value="python" label="Python">

```python
import datahub_sdk, pandas as pd

event = datahub_sdk.Event(
    external_id="door_open",
    type="alarm",
    event_time=pd.Timestamp.now(tz="UTC"))

client.events.create([event])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::events::Event;

let event = Event::new("door_open".into());
api.events.create(&vec![event]).await?;
```

</TabItem>
</Tabs>

## Query

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventRetreiver retriever = new EventRetreiver();
// set filter criteria on the retriever (time range, type, metadata, …)
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
use dataplatform_rust_sdk::filters::EventFilter;

let filter = EventFilter::default();
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
