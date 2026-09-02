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

## The event body {#body}

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID string | The event's identity. Time-ordered UUID v7 — see the note under [Create](#create). |
| `externalId` | string, 3–256 | **Required.** The subject's key in the source system. Shared across events on purpose. |
| `eventTime` | epoch millis, or ISO-8601 on the way in | **Required.** When it happened at the source. Never defaulted — see [Create](#create). |
| `type` | string, 3–128 | Top-level categorization (`alarm`, `work_order`). |
| `subType` | string, 3–128 | Refinement of `type` (`overpressure`). |
| `status` | string, 3–128 | Free-form lifecycle marker (`OPEN`, `acknowledged`). No state machine is enforced. |
| `source` | string, 2–128 | The system of record the event came from (`SAP`, a historian). |
| `description` | string | Prose. This is the field [full-text search](#search) reads. |
| `metadata` | map&lt;string, string&gt; | Flat key/value. An empty key is dropped rather than rejected. |
| `dataSetId` | number | Optional. Platform-internal events (say, anomaly detection on a series outside any data set) legitimately have none. |
| `relatedResources` | object[] | Resources the event is about. Each entry takes an `id`, an `externalId`, or both. |
| `createdTime` | epoch millis | Server-set. When the platform stored it. |
| `lastUpdatedTime` | epoch millis | Server-set. |

`eventTime` and `createdTime` answer different questions and routinely differ by hours: a
gateway that was offline over a weekend backfills Monday morning, so every event it sends
carries a weekend `eventTime` and a Monday `createdTime`. Filter on `eventTime` to ask *when
did it happen*, on `createdTime` to ask *when did we learn about it*.

:::note Numeric ids cross the wire as JSON strings
`dataSetId` and the `id` of each `relatedResources` entry serialize as `"12"`, not `12`. Ids can
exceed the 53-bit integer a JSON number is safe for in JavaScript, and a silently rounded id
is worse than a quoted one. The clients parse them back to integers for you; a hand-rolled
HTTP caller should expect the quotes.
:::

:::note One list, not two parallel ones
`relatedResources` replaced a `relatedResourceIds` / `relatedResourceExternalIds` pair. The two
were independent inputs and drifted: a mismatched pair was unioned into an event describing both
resources, and a patch setting only the external ids left the stored ids stale. There are no
aliases, and events ignore unknown properties, so a client still sending the old field names gets
a `200` with its relations silently dropped. Java SDK users get a compile break on the removed
setters instead.

Supply an `id`, an `externalId`, or both. The server resolves whichever side you left out and
returns both, so a read always gives you the pair. Sending both when they name *different*
resources is a `400` rather than a guess about which one you meant.
:::

## Create {#create}

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
import intellistream_datahub_sdk

event = intellistream_datahub_sdk.Event(
    external_id="door_open",
    type="alarm",
    event_time=datetime.now(timezone.utc))  # required: when the event occurred

client.events.create([event])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use chrono::Utc;
use intellistream_datahub_sdk::events::Event;

let mut event = Event::new("door_open".into());
event.r#type = Some("alarm".into());
event.set_event_time(Utc::now());          // required: when the event occurred
api.events.create(&vec![event]).await?;
```

</TabItem>
</Tabs>

Creating is **all-or-nothing**: if one event in the batch fails validation, none are
written. Attaching the event to resources that do not exist is a `400`, as is a
`dataSetId` naming no data set — so a typo surfaces at write time rather than as an event
that quietly relates to nothing.

Create, update and delete each take at most **10 000 events** per request, and one event
carries at most 10 000 characters of `description`, 256 metadata entries and 100
`relatedResources`. Past any of those is a `400`. [Limits & quotas](./limits) has the rest,
including the daily and lifetime ceilings on how many events an organisation may hold.

:::note Event ids are time-ordered UUID v7
The ingestion paths stamp every event that has no `id` with a **UUID v7** before sending —
`create` in the Python and Rust clients, `ingest(...)` in Java (a plain Java `create` sends
events as-is and lets the server assign ids). The server honors a client-supplied id, which is
what makes retries idempotent: the events table is keyed by `id` and collapses rows that share
one, so re-sending the same event (for example after a
[buffered](./client#durable-ingest-buffering) outage) leaves one row instead of a duplicate.
If you set the `id` yourself, use a time-ordered UUID v7 — a random v4 scatters writes across
that key and hurts insert and query performance. The created event (with its id) is returned
from `create`.
:::

## Look up {#lookup}

Fetch a single event by its UUID, or a batch by any mix of `id` and `externalId`. Ids that
match nothing are **silently omitted** — compare what came back against what you asked for
if a miss matters. A batch is capped at 10 000 ids.

Because an external id is a correlation key, looking one up returns **every** event filed
under it, not one event.

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<EventModel> events = client.events().byIds(List.of(
        IdCollection.createFromExternalId("PO-4500171")));   // every event about this order
```

`IdCollection` carries a numeric id, so the Java client can only look events up by external
id — an event's id is a UUID. Call `POST /events/byids` directly to fetch by UUID.

</TabItem>
<TabItem value="python" label="Python">

```python
events = client.events.by_ids(["PO-4500171"])   # a str selects by external id
events = client.events.by_ids([uuid.UUID("0195f3a2-4c1b-7f9e-9c3a-1b2d4e6f8a90")])
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::events::EventIdCollection;

let events = api.events
    .by_ids(&vec![EventIdCollection::from_external_id("PO-4500171")])
    .await?;
```

</TabItem>
</Tabs>

`GET /events/{id}` fetches one event by UUID and returns `404` when there is none — the one
place a missing event is an error rather than an omission.

## Query

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventRetreiver retriever = new EventRetreiver();
retriever.setLimit(50);
retriever.getFilter().setType(List.of("alarm"));
DataWrapper<EventModel> events = client.events().filter(retriever);
```

</TabItem>
<TabItem value="python" label="Python">

```python
filter = intellistream_datahub_sdk.EventFilter(
    basic_filter=intellistream_datahub_sdk.BasicEventFilter(type="alarm"),
    limit=50)
events = client.events.filter(filter)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::filters::{BasicEventFilter, EventFilter};

let filter = EventFilter::default()
    .set_filter(BasicEventFilter { r#type: Some(vec!["alarm".into()]), ..Default::default() })
    .set_limit(50)
    .build();
let events = api.events.filter(&filter).await?;
```

</TabItem>
</Tabs>

`limit` defaults to **100** and is capped at **10 000**; a zero or negative value falls back
to 100 rather than returning nothing. Whatever you ask for, the result is intersected with
the data sets your token may read — a filter can never widen access, so an empty page can
mean "no matches" or "none you may see", and the two are not distinguished.

### Filtering {#filtering}

Every field you supply is combined with **AND** — an event must match all of them.

| Field | Matching |
| --- | --- |
| `type`, `subType`, `status`, `source` | Pattern match. `*` and `%` are wildcards, `_` is literal. |
| `externalId` | Pattern match, on the same rules. Literal entries are case-sensitive (see the note below). |
| `metadata` | Every key/value pair given must be present on the event. |
| `dataSetId` | Events belonging to these data sets. |
| `relatedResources` | Events attached to these resources. |
| `eventTime`, `createdTime`, `lastUpdatedTime` | `{ "min": …, "max": … }` bounds — see the note below. |

Each field above takes **either a bare value or an array**, and the entries of an array are
combined with **OR**. That is why they are named in the singular: asking for one thing is the
common case and reads as `"type": "alarm"`, while asking for several reads as
`"type": ["alarm", "warning"]`. The exceptions are `metadata` and `relatedResources`, whose entries
must **all** match; they keep plural names for exactly that reason, because adding an entry there
narrows the result where adding a `type` widens it.

There is no `id` field. An event's id is a UUID string, so use [`byids`](#lookup) to fetch by id.

`dataSetId` and `relatedResources` take the same shape: each entry is `{"id": …}` **or**
`{"externalId": …}`, and the two can be mixed in one list:

```json
{
  "filter": {
    "type": ["alarm", "warning"],
    "dataSetId": [{ "id": "43" }, { "externalId": "data_set_sap" }],
    "relatedResources": [{ "externalId": "klp_pipe_ws_a1212_dl" }]
  },
  "limit": 50
}
```

:::note Literal `externalId` entries are case-sensitive here
Unlike the resource, data set and timeseries filters, an `externalId` entry **without** a wildcard
is matched case-sensitively: every event writer hashes the external id verbatim, so the stored key
for `shift_report_1` is not the key for `SHIFT_REPORT_1`. An entry **with** a wildcard is matched
case-insensitively, so `"SHIFT_REPORT_1*"` is the case-insensitive way to ask the same question.
:::

**A parent data set stands in for its children.** Naming one covers everything beneath it in the
`BELONGS_TO` hierarchy, which is the same expansion access control applies to a grant, so the two
now agree.

An `externalId` that names no data set contributes nothing. That can only ever narrow the
result — a typo gives you too few events, never events you should not see.

:::caution Omitting `dataSetId` and sending `[]` are opposites
Omit the field (or send `null`) for **no data set restriction**. An explicit empty list means
**narrow to no data sets**, which matches nothing.

The distinction matters if you build the filter programmatically: code that collects data set
references into a list and always sets the field will silently return zero events when that list
comes back empty, rather than the unrestricted result the same code returns for every other
filter field.
:::

:::note `eventTime.max` is exclusive; the other maxima are inclusive
`eventTime` is matched as `min <= t < max`, while `createdTime` and `lastUpdatedTime` are
matched as `min <= t <= max`. That makes back-to-back `eventTime` windows tile cleanly —
`[Monday, Tuesday)` then `[Tuesday, Wednesday)` covers every event exactly once — where the
same pattern on `createdTime` double-counts the boundary millisecond.
:::

### Advanced filters {#advanced-filters}

`advancedFilter` sits alongside `filter` and builds a boolean expression when flat AND is not
enough — "type is alarm **or** the source is SAP", or "everything except the `test_` prefix".
Combine with `and`, `or` and `not`; the leaves take one of three operators:

| Operator | Meaning |
| --- | --- |
| `equals` | `property` equals `value`. |
| `prefix` | `property` starts with `value`. |
| `in` | `property` is one of `values`. |

Filterable properties are `id`, `externalId`, `type`, `subType`, `source`, `dataSetId` and
`metadata`. Anything else is rejected with a `400` naming the offending property, rather than
being ignored.

```json
{
  "filter": { "type": "alarm" },
  "advancedFilter": {
    "or": [
      { "equals": { "property": ["source"], "value": "SAP" } },
      { "prefix": { "property": ["externalId"], "value": "PO-" } }
    ]
  },
  "limit": 200
}
```

Two things to know. `property` is a list, but only its **first** entry is read — there is no
nested path into `metadata`. And every value is compared as a string, so `dataSetId` matches
`"43"`, not `43`.

### Ordering and paging {#paging}

Events come back **`eventTime` ascending** unless you say otherwise — that is the order the
cursor pages in, so paging does not change the order underneath you. Ask for another with
`sort`, over `eventTime`, `createdTime`, `lastUpdatedTime`, `externalId`, `type`, `subType`,
`status`, `source` or `dataSetId`:

```json
{ "filter": { "type": "alarm" },
  "sort": { "property": ["eventTime"], "order": "desc" },
  "limit": 200 }
```

Only the **first** `property` is used, and `id` is appended behind it — a sort column alone is
not a position unless it is unique, and a page boundary inside a run of equal values repeats or
drops exactly those rows. A property that is not sortable is ignored rather than rejected, and
any `order` that is not exactly `desc` sorts ascending — a malformed sort degrades to the
default instead of silently reversing your results. Null values sort last ascending, first
descending.

To walk past the first page, echo back the `nextCursor` the response carried:

```json
{ "filter": { "type": "alarm" },
  "sort": { "property": ["eventTime"], "order": "desc" },
  "cursor": "djE6ZXZlbnRUaW1lfGRlc2N8MTc1NDQ3NjUyMjEwNHwwMTk1ZjNhMg",
  "limit": 200 }
```

The cursor is **opaque** — base64 of a versioned encoding carrying the sort, the boundary value
and the id — so do not build or parse one. A cursor that does not decode restarts the walk from
the first page rather than failing, which is obviously wrong to a caller, where guessing at half
a position would silently skip or repeat the rows around the boundary.

Send it with the **same** `sort` that produced it: a cursor is a position in one particular
order. Continuing it under another is refused, though today the refusal arrives as an empty
response rather than a clean 400. Sorting by `subType` or `status` cannot be paged at all —
both columns are nullable, and a keyset boundary on them would skip the events that have no
value.

Prefer this to counting pages. Events are stored partitioned by event time, so resuming from
a position lets whole partitions be skipped, where an offset re-reads everything ahead of it
and gets slower the further you page. Page 400 costs what page 1 costs. The trade is that
there is no random access: you walk forward from where you were and cannot jump to page 7.
`nextCursor` is absent on a short page, so "keep going while it is present" is the whole loop —
and since a full page may still be the last, a complete walk ends with one empty request.

All three clients read the cursor off the response envelope rather than off the last event:

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
DataWrapper<EventModel> page = client.events().filter(retriever);
if (page.getNextCursor() != null) {
    retriever.setCursor(page.getNextCursor());   // keep the same sort
}
```

</TabItem>
<TabItem value="python" label="Python">

```python
page = client.events.filter(filter)
if page.next_cursor is not None:
    filter.cursor = page.next_cursor             # keep the same sort_by / sort_order
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
let page = api.events.filter(&filter).await?;
if let Some(cursor) = page.next_cursor() {
    filter.set_cursor(cursor);                   // keep the same sort
}
```

</TabItem>
</Tabs>

## Policy findings {#policy-findings}

A **policy finding** — a naming-policy violation that was allowed through and recorded for a
steward — is an ordinary event. There is no findings endpoint and no findings client: they are
written to the event store like anything else, so everything on this page already works on
them.

The encoding is a wire contract, so you can read findings without a policy-aware client:

| Field | Holds |
| --- | --- |
| `type` | Always `policy_finding`. Matched exactly, never by prefix — this is the one filter separating findings from the tenant's real events. |
| `subType` | Which policy fired, by its external id. |
| `source` | `datahub_policy_<policy external id>`, truncated to 128 characters. |
| `externalId` | `policy_finding_<policy external id>_<node id>` — the correlation key every event in one finding's lifecycle shares. |
| `status` | `OPEN` or `RESOLVED` — what *this event* asserts, not the finding's current state. |
| `description` | What is wrong, in words. |
| `relatedResources` | The entity the finding is about, by node id. |
| `dataSetId` | That entity's data set. |
| `metadata` | `offendingValue`, `suggestion` (when one could be derived), `raisedBy`. |

Note the external id is keyed on the entity's **node id**, not its external id. The external
id is the offending value here — the thing a steward is most likely to change — and keying on
it would mean renaming a resource silently abandoned its finding and started a second stream.

### Fetch the queue

Filter on the type, ascending by `eventTime`, and page with [`after`](#paging):

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
EventRetreiver retriever = new EventRetreiver();
retriever.getFilter().setType(List.of("policy_finding"));
retriever.getFilter().setSubType(List.of("naming_snake_case"));   // one policy; omit for all
retriever.setLimit(200);
retriever.getSort().setProperty(List.of("eventTime"));
retriever.getSort().setOrder("asc");

DataWrapper<EventModel> findings = client.events().filter(retriever);
```

</TabItem>
<TabItem value="python" label="Python">

```python
filter = intellistream_datahub_sdk.EventFilter(
    basic_filter=intellistream_datahub_sdk.BasicEventFilter(
        type="policy_finding",
        sub_type="naming_snake_case"),   # one policy; omit for all
    limit=200)

findings = client.events.filter(filter)
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use intellistream_datahub_sdk::filters::{BasicEventFilter, EventFilter};

let filter = EventFilter::default()
    .set_filter(BasicEventFilter {
        r#type: Some(vec!["policy_finding".into()]),
        sub_type: Some(vec!["naming_snake_case".into()]),   // one policy; omit for all
        ..Default::default()
    })
    .set_limit(200)
    .build();

let findings = api.events.filter(&filter).await?;
```

</TabItem>
</Tabs>

### Fold the stream

A finding's current state is **not stored** — you derive it. Nothing is ever updated in place:
raising appends an `OPEN`, resolving appends a `RESOLVED` carrying the same `externalId`. Group
by external id, order by `eventTime` ascending, and the last event wins:

<Tabs groupId="lang">
<TabItem value="java" label="Java">

```java
Map<String, EventModel> current = new HashMap<>();
findings.getItems().stream()
        .sorted(Comparator.comparing(EventModel::getEventTime))
        .forEach(e -> current.put(e.getExternalId(), e));   // last write wins

List<EventModel> open = current.values().stream()
        .filter(e -> "OPEN".equals(e.getStatus()))
        .toList();
```

</TabItem>
<TabItem value="python" label="Python">

```python
current = {}
for e in sorted(findings, key=lambda e: e.event_time):
    current[e.external_id] = e          # last write wins

open_findings = [e for e in current.values() if e.status == "OPEN"]
```

</TabItem>
<TabItem value="rust" label="Rust">

```rust
use std::collections::HashMap;

let mut events = findings.get_items().clone();
events.sort_by_key(|e| e.event_time);

let mut current: HashMap<String, _> = HashMap::new();
for e in events {
    current.insert(e.external_id.clone(), e);   // last write wins
}

let open: Vec<_> = current.values().filter(|e| e.status.as_deref() == Some("OPEN")).collect();
```

</TabItem>
</Tabs>

:::caution Do not filter on `status`
A stored `OPEN` event means *this was raised*, not *this is outstanding*. Filtering the query
on `status: "OPEN"` returns the raise of every finding that has since been resolved — the
resolve is a separate, later event, and narrowing the query hides it. Open-ness is a
conclusion drawn from the stream, not a fact the store holds, so fetch and fold.

Order ascending for the same reason: replay out of order and a stale `OPEN` overwrites the
`RESOLVED` that followed it. Keep folding across pages too — a `RESOLVED` on page 3 closes a
finding whose `OPEN` arrived on page 1.
:::

:::caution A fold needs the *whole* stream, so a truncated page lies
Folding is only correct if every event sharing an external id is in front of you. Get one
page of a queue larger than your `limit` and an `OPEN` can arrive without the `RESOLVED` that
closed it — the fold then reports a resolved finding as outstanding. It is a wrong answer,
not an error, and nothing in the response marks it as partial.

Page until short — a full page is a signal that there is more, never that you have it all.
Narrowing by `subType` and `dataSetId` keeps the walk cheap, but it is paging, not narrowing,
that makes the fold correct.
:::

Raising is idempotent: a raise event's id is derived from what it asserts, so re-evaluating an
entity whose external id has not changed collapses onto the raise already stored. An entity
written a thousand times contributes one `OPEN`, not a thousand. A raise for a *different*
non-conforming value is a new fact and is appended — which is also all "reopening" is.

For the steward's side of this — how to resolve a finding, what resolving means, and why
findings are raised for resources but never for events — see
[Findings](./external-ids#findings).

## Full-text search {#search}

`POST /events/search` is a case-insensitive **substring** match over `externalId`, `description`
and the metadata values, returned newest first by `eventTime`.

It is not word-aware, and it does not rank: events live in ClickHouse and have no full-text index,
so `pump` finds `pump` and `pumps` but not `pumping`, and rows come back newest first rather than
best-match first. The three node-backed searches do rank by relevance. It accepts the same `filter` block as `POST /events/filter`, which
narrows the phrase's hits:

```json
{
  "search": { "query": "overpressure" },
  "filter": { "type": ["alarm"], "eventTime": { "min": 1745241600000 } },
  "limit": 50
}
```

:::note What changed
`filter` used to be accepted and silently ignored here, as it was on the resource and data set
searches. All four searches now apply it. `dataSetId` covers everything beneath the data sets you
name, exactly as it does on `/events/filter`.

The description above is also a correction: this endpoint never was fuzzy, word-aware or
relevance-ranked, whatever the previous wording said.
:::

`query` must be 3 to 140 characters. There is no character restriction beyond that: punctuation,
underscores and non-Latin scripts are all accepted, so an externalId or a Cyrillic asset name can
be searched for directly. `limit` here is capped at **1 000**, lower than the 10 000 of `filter`.

Reach for `filter` instead whenever the question is structured (a time range, an exact type, a
related resource). It is faster and its results are predictable.

## Distinct values {#distinct-values}

Two families of endpoint answer "what values actually occur?" — the material for a filter
drop-down or a type-ahead, without scanning events yourself. Both are restricted to the data
sets your token may read, so a UI built on them cannot offer a facet the user could not then
query.

| Endpoint | Returns |
| --- | --- |
| `GET /events/list/types` | Every distinct `type`, alphabetically. |
| `GET /events/list/sub-types` | Every distinct `subType`. |
| `GET /events/list/statuses` | Every distinct `status`. |
| `GET /events/list/sources` | Every distinct `source`. |
| `GET /events/search/type?q=` | Distinct `type` values containing `q`, case-insensitive. |
| `GET /events/search/sub-type?q=` | The same for `subType`. |
| `GET /events/search/status?q=` | The same for `status`. |
| `GET /events/search/source?q=` | The same for `source`. |

Both families take `limit` (default 1 000, clamped to 1–10 000). The `search/*` form requires
`q` and returns `400` without it.

```
GET /events/search/type?q=alarm&limit=20
→ { "items": ["alarm", "alarm_cleared", "pre_alarm"] }
```

## Count {#count}

`GET /events/count` returns `{ "count": 148392 }` for the tenant. It is a single cheap query,
and it takes **no filters** — for a filtered count, run `POST /events/filter` with the `limit`
you care about and measure the page.

## Update {#update}

`POST /events/update` changes fields on events that already exist. Identify each one by UUID
`id` or by `externalId`, and name only the fields you want changed — anything you leave out
keeps its current value.

Each field is an object carrying a verb rather than a bare value, which is what lets "clear
this" be expressed distinctly from "leave it alone":

| Verb | Applies to | Effect |
| --- | --- | --- |
| `set` | every field | Replace the value. |
| `setNull: true` | nullable fields only | Clear the value. `externalId`, `type` and `eventTime` are not nullable, so asking to clear any of them is a `400`. |
| `add` | `metadata`, `relatedResources` | Merge entries in, keeping the rest. |
| `remove` | the same collections | Take entries out, keeping the rest. A `relatedResources` entry matches on either side, so you can remove by `id` or by `externalId` whichever you have. |

```json
{
  "items": [
    {
      "externalId": "alarm_pipe_overpressure_2026_04_22_14_30",
      "update": {
        "status": { "set": "acknowledged" },
        "metadata": { "add": { "acked_by": "olav" } }
      }
    }
  ]
}
```

Updatable fields are `externalId`, `description`, `type`, `subType`, `status`, `source`,
`dataSetId`, `metadata`, `eventTime` and `relatedResources`. `eventTime` is set from an
ISO-8601 string. Sending both `set` and `setNull` for one field is
a `400` — the request is contradictory, so it is refused rather than resolved by precedence.

`setNull` is refused on the three fields a create cannot omit: `externalId`, `type` and
`eventTime`. Clearing `type` used to be accepted, and it left the event unreadable by any
client that models `type` as required, so the read failed rather than the write. `dataSetId`
is the one field here that genuinely is nullable: `setNull` detaches the event from its data
set, and naming a `dataSetId` that no data set has is a `400` rather than a stored dangling
reference.

:::caution Prefer a follow-up event to mutating one
An event update runs a replace-and-cleanup on the stored record. While it is in flight, a
concurrent read of the same event can briefly return the pre-update version *or* see it
twice. Where the record matters for audit, write a new event that corrects the old one
instead: that is what an append-only log is for, and it keeps the correction itself visible.

`status` is the honourable exception — acknowledging an alarm in place is what the field is
there for.
:::

`source` is worth one warning: create accepts up to 128 characters, but the update path
rejects anything over **64**. A value in between can be written and then not modified.

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

Deletes are **idempotent**: removing an event that is already gone returns `200` and changes
nothing, so a retried delete needs no bookkeeping.

Remember that an external id names a *subject*, not an event. Deleting by external id removes
**every event filed under it**, which is rarely what you want for a single mistaken record —
delete that one by its UUID.

:::caution A `200` means "accepted", not "gone"
The delete is published to the ingestion pipeline and marked in the backend without waiting
for the removal to land — a background job does the actual work. Until it has run, the event
**can still come back from `filter` and `byids`**.

So a test that deletes an event and immediately asserts it is gone will flake, and so will a
UI that re-queries straight on the back of a delete. Poll until the event disappears rather
than reading once, and treat its absence — not the `200` — as the signal. The same eventual
consistency applies in the other direction: an event is not necessarily queryable the instant
`create` returns.

Once the background job has run the removal is permanent, and anything referencing the event
by id stops resolving.
:::

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

## What each client covers {#client-coverage}

The three clients cover the write and read paths, including the facet endpoints; the
administrative ones are HTTP-only so far.

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| Create | `events().create` / `ingest` | `events.create` | `events.create` |
| Get by id | `events().getById` | `events.get` | `events.get` |
| Look up by id / external id | `events().byIds` | `events.by_ids` | `events.by_ids` |
| Filter | `events().filter` | `events.filter` | `events.filter` |
| — with `sort` | `EventRetreiver.sort` | `sort_by` / `sort_order` | `set_sort` |
| — with paging | `EventRetreiver.cursor` | `cursor` | `set_cursor` |
| Update | `events().update` | `events.update` | `events.update` |
| Full-text search | `events().search` | `events.search` | `events.search` |
| Count | `events().count` | `events.count` | `events.count` |
| Delete | `events().delete` | `events.delete` | `events.delete` |
| Distinct values | `events().listTypes` etc. | `events.list_types` etc. | `events.list_types` etc. |

All three carry the same four pairs: `list_types` / `search_types` and the same for sub-types,
statuses and sources (`listTypes` / `searchTypes` … in Java).

Take the paging value from the response envelope — `getNextCursor()` in Java, `page.next_cursor`
in Python, `page.next_cursor()` in Rust — and send it back unchanged. It is opaque; the
`<millis>_<id>` value earlier versions had you assemble by hand no longer decodes, and an
undecodable cursor restarts the walk from the first page.
