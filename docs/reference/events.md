---
sidebar_position: 6
title: Events
---
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Events

Record and query operational events.

:::info An event's `externalId` is a correlation key, not an identity
This is the opposite of what it means on a resource, and it is deliberate. An event's
external id is the **source system's key for the subject** the event is about — an order, a
permit, a batch — so **many events share one**. "Everything that happened to `PO-4500171`"
is one indexed lookup, and that is what makes the log an audit trail.

No uniqueness is enforced, and none ever will be. Per-event identity is the event `id`
below. Naming policies do not apply to events either; only the
[charset floor](./external-ids#the-charset-floor) does, so `21-PT-1234` is accepted on an
event even when a `snake_case` policy is rejecting it on resources.
[The two contracts →](./external-ids#the-two-contracts)
:::

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

### Filtering {#filtering}

Alongside the scalar matches (`type`, `subType`, `status`, `source`, `externalIdPrefix`) and the
time ranges (`eventTime`, `createdTime`, `lastUpdatedTime`), two fields narrow by reference:

| Field | Restricts to |
| --- | --- |
| `dataSetIds` | Events belonging to these data sets |
| `relatedResources` | Events attached to these resources |

Both take the same shape — each entry is `{"id": …}` **or** `{"externalId": …}`, and the two can
be mixed in one list:

```json
{
  "filter": {
    "type": "alarm",
    "dataSetIds": [{ "id": "43" }, { "externalId": "data_set_sap" }],
    "relatedResources": [{ "externalId": "klp_pipe_ws_a1212_dl" }]
  },
  "limit": 50
}
```

**Data sets match exactly.** A parent data set does not stand in for its children, so list every
data set you want rather than relying on the hierarchy. This is the one place data set behaviour
differs from access control, where a grant on a parent *does* cover its descendants.

An `externalId` that names no data set contributes nothing. That can only ever narrow the
result — a typo gives you too few events, never events you should not see.

:::caution Omitting `dataSetIds` and sending `[]` are opposites
Omit the field (or send `null`) for **no data set restriction**. An explicit empty list means
**narrow to no data sets**, which matches nothing.

The distinction matters if you build the filter programmatically: code that collects data set
references into a list and always sets the field will silently return zero events when that list
comes back empty, rather than the unrestricted result the same code returns for every other
filter field.
:::

### Ordering and paging {#paging}

By default a query returns matching events in no particular order. Ask for an order with
`sort`, over `eventTime`, `createdTime`, `lastUpdatedTime`, `externalId`, `type`, `subType`,
`status`, `source` or `dataSetId`:

```json
{ "filter": { "type": "alarm" },
  "sort": { "property": ["eventTime"], "order": "desc" },
  "limit": 200 }
```

To walk past the first page, send back a `cursor` rather than an offset. It is
`<eventTime epoch millis>_<id>`, taken from the last event you saw:

```json
{ "filter": { "type": "alarm" },
  "sort": { "property": ["eventTime"], "order": "asc" },
  "cursor": "1754476522104_0195f3a2-4c1b-7f9e-9c3a-1b2d4e6f8a90",
  "limit": 200 }
```

Two things to know about this. Both halves are required: event times are not unique — a
bulk ingest lands thousands of events in the same millisecond — so a cursor on the timestamp
alone would either skip that group or repeat it forever, and the `id` breaks the tie. A value
that does not parse is ignored and the walk restarts from the beginning, rather than a half-read
cursor quietly returning the wrong page. And a cursor fixes the order to `eventTime` then `id`
ascending, overriding `sort`, because a cursor read back in a different order silently skips
rows instead of failing.

Prefer this to counting pages. Events are stored partitioned by event time, so resuming from
a timestamp lets whole partitions be skipped, where an offset re-reads everything ahead of it
and gets slower the further you page. A short page is the last page.

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
