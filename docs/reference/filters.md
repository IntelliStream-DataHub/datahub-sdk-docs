---
sidebar_position: 2.5
title: Filters
---
# Filters

Every collection read takes a filter object rather than a list of query parameters. The same
few shapes recur across the node types, so this page describes the shared grammar once; the
per-endpoint pages say which filter each call takes and what it returns.

The examples here only build filters. Nothing on this page calls the API, so none of it needs
a seeded tenant; [Events](./events#filtering) has the worked queries.

## How a field is shaped {#field-shape}

A filter field that ORs its entries is named in the **singular** and takes either a bare value
or a list, so `"type": "Alarm"` and `"type": ["Alarm", "Warning"]` are both valid and mean
"either". The two exceptions, `labels` and `relatedResources`, keep plural names because their
entries **AND** together: a second entry narrows the result where a second `type` would widen
it. `metadata` behaves the same way.

Text entries are literal or wildcard:

| Character | Meaning |
| --- | --- |
| `*` | Any run of characters |
| `%` | The same, so a caller who thinks in SQL is not surprised |
| `_` | **Literal.** External ids are built out of underscores, so `sap_work_orders` means that id and not `sapXwork_orders` |

One list mixes both freely — `["sap_work_orders", "plant_*", "*_archive"]` is exact lookup,
prefix search and contains search in a single call. Entries without a wildcard resolve through
an index; only the patterns need a scan, so an exact lookup keeps its index however many
patterns share the list. Every OR'd text list is capped at 1000 entries.

Case sensitivity differs in one place, and it is worth knowing which:

| Filter | Literal entry | Wildcard entry |
| --- | --- | --- |
| Node filters (`externalId`, `name`, `source`) | Case-**in**sensitive | Case-insensitive |
| `EventFilter.externalId` | Case-**sensitive** | Case-insensitive, through `ILIKE` |

Events are the odd one out because every event writer hashes the external id verbatim, so the
stored key for `shift_report_1` is not the key for `SHIFT_REPORT_1`; nodes lowercase before
hashing and match either. Writing the entry as a wildcard — `"SHIFT_REPORT_1*"` — is the way to
ask an event question case-insensitively.

## The node filter family {#node-filters}

Every node filter inherits the same eight fields.

| Field | Type | Combines | Meaning |
| --- | --- | --- | --- |
| `id` | list&lt;long&gt; | OR | Node ids. Serialised as strings on the wire, so a JavaScript client cannot round them through a double. |
| `externalId` | list&lt;string&gt; | OR | Pattern list over external ids. |
| `name` | list&lt;string&gt; | OR | Pattern list over names. |
| `source` | list&lt;string&gt; | OR | Pattern list over originating systems. |
| `labels` | list&lt;string&gt; | **AND** | Labels the node must carry, all of them. Names are canonicalised, so `"pump a"` finds the label stored as `PUMP_A`. A name matching no label matches no nodes. |
| `metadata` | map&lt;string, string&gt; | **AND** | Entries that must all be present. A null value matches the key alone. |
| `createdTime` | [`TimeFilter`](#timefilter) | AND | Window on record creation. |
| `lastUpdatedTime` | [`TimeFilter`](#timefilter) | AND | Window on last update. |

Two things build on that base:

- **`DataSetFilter` adds nothing.** A data set *is* the scope other nodes are filtered by, so it
  has no `dataSetId` of its own — the eight fields above are the whole filter.
- **Resource, time-series and function filters add `dataSetId`**, a list of
  [`IdCollection`](#idcollection) references. A data set stands in for everything beneath it in
  the `BELONGS_TO` hierarchy, so naming a parent covers its children — the same expansion the
  data set ACL applies. An external id naming no data set contributes nothing.

`dataSetId` is the one list where **null and empty mean opposite things**:

| Sent | Meaning |
| --- | --- |
| Field omitted, or `null` | No data set restriction |
| `[]` | Narrow to no data sets — matches nothing |

The field was once a scalar `Long`, so the old shape still fails loudly rather than quietly:
`"dataSetId": 43` is a bare number where an object is expected and the request is rejected.
Send `{"id": "43"}` or an external id instead.

## Event filters {#event-filters}

An event query has two layers: an outer retriever carrying paging and ordering, and an inner
`EventFilter` carrying the predicates.

The inner filter shares `externalId`, `source`, `metadata`, `createdTime`, `lastUpdatedTime`
and `dataSetId` with the node filters above — same names, same types, same semantics, pinned by
a parity test since the compiler cannot enforce it. On top of those it adds:

| Field | Type | Combines | Meaning |
| --- | --- | --- | --- |
| `type` | list&lt;string&gt; | OR | Pattern list over event types. |
| `subType` | list&lt;string&gt; | OR | Pattern list over sub-types. |
| `status` | list&lt;string&gt; | OR | Pattern list over lifecycle statuses. |
| `eventTime` | [`TimeFilter`](#timefilter) | AND | Window on when the event occurred, as distinct from when the record was written. |
| `relatedResources` | list&lt;[`IdCollection`](#idcollection)&gt; | **AND** | The event must relate to all of these. Each entry may carry an `id`, an `externalId`, or both. |

There is **no `id` field on an event filter**. Look an event up by id through
[`byIds`](./events#lookup) instead.

The outer retriever carries `limit`, `cursor`, `sort` and `advancedFilter` — a PostgreSQL-flavoured
boolean expression that is AND-combined with the inner filter.
[Events](./events#filtering) documents all four, with the query examples.

## Retrieving datapoints {#retrievefilter}

Datapoint retrieval is not a node filter: it selects points within one series by time window
rather than nodes by their columns. One filter is one series, so reading several means passing
several filters.

| Field | Type | Meaning |
| --- | --- | --- |
| `externalId` | string | The series, by external id. |
| `id` | long | The series, by numeric id. Serialised as a string. |
| `start` / `end` | timestamp | The window. **At least one is required.** |
| `limit` | integer | Maximum datapoints, 0 to 100 000. Defaults to `0`; an explicit null becomes 100. |
| `aggregates` | list&lt;string&gt; | Aggregates to compute instead of raw points. |
| `granularity` | string | Bucket size for `aggregates`, e.g. `1h`. |
| `includeOutsidePoints` | boolean | Include the points bracketing the window. Defaults to `false`. |
| `mergeDuplicates` | boolean | Collapse points sharing a timestamp. Defaults to `false`. |
| `cursor` | string | Continuation from a previous page, see [paging](#paging). |

## Shared pieces {#shared}

### IdCollection {#idcollection}

Wherever a filter references another entity, it does so by id or by external id, in the same
shape:

```json
[{"id": "43"}, {"externalId": "data_set_sap"}]
```

`id` travels as a JSON string even though it is a number, for the precision reason above.

### TimeFilter {#timefilter}

A closed window, both bounds optional:

```json
{"min": 1754476522104, "max": 1754480122104}
```

### Sorting {#sorting}

`sort` carries a `property` list and an `order`. There is deliberately **no `nulls` option** —
where nulls sit follows the direction. A `nulls` field did exist and was removed, so sending
one now is an unknown field and a `400`.

### Default sizes {#defaults}

| | Value |
| --- | --- |
| Default page size | 1000 |
| Maximum page size | 10 000 |

The maximum is a cap on one page, not a ceiling on how much you can read — walk past it with a
cursor.

## Paging with a cursor {#paging}

A listing that has more to give returns a cursor on the envelope. It is **opaque**: base64, no
version tag, and its contents are ours to change. Echo back exactly what you were handed rather
than assembling one.

A cursor is only meaningful against the order it was produced in, so it must travel with the
same `sort`. Three things are refused with a `400`
[`.../errors/malformed-cursor`](./client#problem-documents):

- a value that is not readable as a cursor,
- one whose row reference is not a valid id,
- one produced by a different sort than the request asks for.

None of them restarts the walk silently, which would loop a paging client or skip rows.
[Events](./events#paging) has the walk.
