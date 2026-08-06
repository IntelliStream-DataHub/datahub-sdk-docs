---
sidebar_position: 5
title: Events
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Events

An **event** is a record that something happened — an alarm fired, a work order was
raised, a machine changed state. Where a time-series answers *what was the value at
time T*, an event answers *what occurred, and when*.

Two properties shape the rest of this page:

- An event is **anchored in time by `eventTime`** — the moment it occurred at the source,
  which is not the moment you sent it. The SDK deliberately does *not* default this to
  "now": an event without it is rejected rather than silently mis-timestamped.
- An event is **identified by `externalId`**, and that id is not required to be unique
  over time. Events sharing an `externalId` form the lifecycle of one logical thing — a
  purchase order moving `created → approved → paid` is four events, one id.

Events also carry free-form `type`/`subType` for classification, a `metadata` map for
structured detail, and links to the resources they concern.

## The event model

`externalId`, `type` and `eventTime` are the fields you must set; everything else is
optional and may be left unset.

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `externalId` | **yes** | string | Stable snake_case id, 3–256 chars. Not unique over time — see above. |
| `type` | **yes** | string | Classification, 3–128 chars (e.g. `alarm`). |
| `eventTime` | **yes** | timestamp | When the event occurred at the source. Must be timezone-aware. |
| `subType` | no | string | Finer classification, 3–128 chars (e.g. `electrical`). |
| `description` | no | string | Human-readable summary. |
| `status` | no | string | Free-form lifecycle state (e.g. `open`, `COMPLETE`, `FAILED`). |
| `source` | no | string | System the event came from. |
| `metadata` | no | map&lt;string, string&gt; | Structured detail. Values are strings — numbers must be stringified. |
| `dataSetId` | no | integer | Owning data set. Governs access and makes the event addressable by data set. |
| `id` | no | UUID | Server-assigned if omitted. See the note on UUID v7 below. |

Construction differs by language — Java uses a no-arg model plus setters, Python a
keyword constructor, Rust a `new` taking the external id plus field assignment:

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventModel event = new EventModel();
event.setExternalId("door_open");          // required
event.setType("alarm");                    // required
event.setEventTime(ZonedDateTime.now());   // required: when the event occurred

event.setSubType("electrical");            // optional from here down
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
    event_time=datetime.now(timezone.utc),      # required: when the event occurred
    sub_type="electrical",                      # optional from here down
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
event.set_event_time(Utc::now());                 // required: when the event occurred

event.sub_type = Some("electrical".into());       // optional from here down
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

## The filter model

Queries are expressed as a filter object rather than method arguments. It has two
layers: an **outer filter** carrying query-wide options like `limit`, and an inner
**basic filter** carrying the field predicates. Every field is optional — an empty
filter matches everything you are allowed to read.

Field predicates are **exact and case-sensitive**, and they combine with AND. Because
`type`, `subType` and `source` are tenant-defined free-form strings, discover the values
in use rather than guessing at them.

| Field | Layer | Type | Notes |
| --- | --- | --- | --- |
| `limit` | outer | integer | Maximum events returned. |
| `type` | basic | string | Exact match. |
| `subType` | basic | string | Exact match. |
| `source` | basic | string | Exact match. |
| `status` | basic | string | Exact match. |
| `externalIdPrefix` | basic | string | Prefix match on `externalId`. |
| `start` / `end` | basic | timestamp | Window on `eventTime`, `start` inclusive, `end` exclusive. |
| `dataSetIds` | basic | list&lt;IdCollection&gt; | Restrict to these data sets — see below. |

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventRetreiver retriever = new EventRetreiver();
retriever.setLimit(50);
retriever.getFilter().setType("alarm");
```

</TabItem>
<TabItem value="python" label="Python">

```python
filter = datahub_sdk.EventFilter(
    basic_filter=datahub_sdk.BasicEventFilter(type="alarm"),
    limit=50)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use dataplatform_rust_sdk::filters::{BasicEventFilter, EventFilter};

let filter = EventFilter::default()
    .set_filter(BasicEventFilter { r#type: Some("alarm".into()), ..Default::default() })
    .set_limit(50)
    .build();
```

</TabItem>
</Tabs>

### Restricting to data sets

`dataSetIds` takes a list of references, each naming a data set by **id or externalId** —
the same `IdCollection` reference used elsewhere in the API. Over the wire
`[IdCollection.createFromId(43L), IdCollection.createFromExternalId("data_set_sap")]`
becomes `[{"id": 43}, {"externalId": "data_set_sap"}]`; browser clients should send ids
as strings, since they exceed JavaScript's safe integer range.

A reference matches that data set **exactly** — unlike a read grant, it does not extend
to data sets beneath it in the hierarchy, so list every one you want. Omitting the field
applies no restriction (you still only see data sets you may read), whereas an explicit
empty list `[]` narrows to nothing and matches no events.

## Service functions

The event service hangs off the client — `client.events()` in Java, `client.events` in
Python, `api.events` in Rust.

### create

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

### ingest (Java)

For high-throughput writes, `ingest` chunks, parallelises and retries events the same
way as datapoints, returning the same [`IngestResult`](./timeseries.md#ingestresult)
tuned with the same [`IngestOptions`](./timeseries.md#ingestoptions). It is also the
Java path that stamps client-side UUID v7 ids.

```java
IngestResult result = client.events().ingest(events,
        IngestOptions.builder().batchSize(1_000).parallelism(8).build());
```

In Python and Rust, `create` already batches — use it with a large list instead.

### filter

Takes a filter from [the filter model](#the-filter-model) and returns the matching
events.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<EventModel> events = client.events().filter(retriever);
```

</TabItem>
<TabItem value="python" label="Python">

```python
events = client.events.filter(filter)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
let events = api.events.filter(&filter).await?;
```

</TabItem>
</Tabs>

### delete

Takes id or external-id references and deletes them together.

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
