---
sidebar_position: 5
title: Events
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Events

Records of things that happened — an alarm firing, a work order raised, a machine
changing state. Where a time-series answers *what was the value at time T*, an event
answers *what occurred, and when*. Events are anchored in time by `eventTime`, the moment
they occurred at the source, and classified by free-form `type`/`subType`.

## Event fields

`externalId`, `type` and `eventTime` are the fields you must set; everything else is
optional. An event without an `eventTime` is rejected rather than silently stamped with
"now" — the moment it occurred at the source is rarely the moment you sent it.

`externalId` is **not** required to be unique over time. Events sharing one form the
lifecycle of a single logical thing: a purchase order moving `created → approved → paid`
is four events under one id.

| Field | Type | Meaning |
| --- | --- | --- |
| `externalId` | string | **Required.** Stable snake_case id, 3–256 chars. |
| `type` | string | **Required.** Classification, 3–128 chars (e.g. `alarm`). |
| `eventTime` | timestamp | **Required.** When the event occurred at the source. Must be timezone-aware. |
| `subType` | string | Finer classification, 3–128 chars (e.g. `electrical`). |
| `description` | string | Human-readable summary. |
| `status` | string | Free-form lifecycle state (e.g. `open`, `COMPLETE`). |
| `source` | string | System the event came from. |
| `metadata` | map | String-to-string. Numbers must be stringified. |
| `dataSetId` | integer | Owning data set. Governs access and makes the event addressable by data set. |
| `id` | UUID | Server-assigned if omitted — see below. |

Java uses a no-arg model plus setters, Python a keyword constructor, Rust a `new` taking
the external id plus field assignment:

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventModel event = new EventModel();
event.setExternalId("door_open");          // required
event.setType("alarm");                    // required
event.setEventTime(ZonedDateTime.now());   // required

event.setSubType("electrical");
event.setStatus("open");
event.setDescription("Door 7 forced open");
event.setMetadata(Map.of("door", "7", "site", "oslo"));
```

</TabItem>
<TabItem value="python" label="Python">

```python
from datetime import datetime, timezone
import datahub_sdk

event = datahub_sdk.Event(
    external_id="door_open",                    # required
    type="alarm",                               # required
    event_time=datetime.now(timezone.utc),      # required
    sub_type="electrical",
    status="open",
    description="Door 7 forced open",
    metadata={"door": "7", "site": "oslo"})
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use chrono::Utc;
use dataplatform_rust_sdk::events::Event;

let mut event = Event::new("door_open".into());   // required: external id
event.r#type = Some("alarm".into());              // required
event.set_event_time(Utc::now());                 // required

event.sub_type = Some("electrical".into());
event.status = Some("open".into());
event.description = Some("Door 7 forced open".into());
event.add_metadata("door".into(), "7".into());
event.add_metadata("site".into(), "oslo".into());
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

## Create

Takes a batch and returns the created events, each with its `id` populated. Pass a
single-element list for one event.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
client.events().create(List.of(event));
```

</TabItem>
<TabItem value="python" label="Python">

```python
client.events.create([event])   # list[Event]
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
api.events.create(&vec![event]).await?;   // Vec<Event>
```

</TabItem>
</Tabs>

## High-throughput ingestion (Java)

`ingest` chunks, parallelises and retries events the same way as datapoints, returning
the same [`IngestResult`](./timeseries.md#ingestresult) tuned with the same
[`IngestOptions`](./timeseries.md#ingestoptions). It is also the Java path that stamps
client-side UUID v7 ids.

```java
IngestResult result = client.events().ingest(events,
        IngestOptions.builder().batchSize(1_000).parallelism(8).build());
```

In Python and Rust, `create` already batches — pass it a large list instead.

## Query

Takes an [`EventFilter`](./filters.md#eventfilter) and returns the matching events.

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

## Delete

Takes [id or external-id references](./filters.md#idcollection) and deletes them together.

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
