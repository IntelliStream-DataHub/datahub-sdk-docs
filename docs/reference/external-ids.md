---
sidebar_position: 2
title: External ids & naming
---

# External ids & naming

`externalId` is how your systems refer to something in DataHub without holding its numeric
id. Two things about it repay reading once, because both are easy to get wrong from the
outside: it **means different things on a resource and on an event**, and **two independent
layers** decide whether a given value is accepted.

## The two contracts

Same field name, different jobs.

| On | What `externalId` is | Unique? |
| --- | --- | --- |
| **Resources, data sets, time-series** | The **identity** of one thing — your key for it, and what every integration matches on. | Yes, per tenant, compared without case |
| **Events** | A **correlation key** — the source system's key for the *subject* the event is about. | **No, and deliberately never** |

An order that is created, amended and then shipped produces three events all carrying
`PO-4500171`. That is the point: the order's history is "every event with this external id,
in time order", and the log is an audit trail because of it. Per-event identity comes from
the platform's own event `id` (a time-ordered UUID v7 — see [Events](./events)), never from
the external id.

:::danger Do not synthesise per-event external ids
Making event external ids unique — `PO-4500171-1`, `PO-4500171-2` — throws away the only
cheap way to ask for a subject's history, and pushes you toward updating events in place,
which destroys the append-only record. If you need to de-duplicate a redelivered snapshot,
set the event `id` yourself; retries then collapse to one row.
:::

## The two layers

### Layer 1 — the charset floor {#the-charset-floor}

Platform-wide, not configurable, and it applies **everywhere an external id is accepted,
events included**.

| | |
| --- | --- |
| Accepted | `A-Z` `a-z` `0-9` and the separators `. _ : + = -` |
| Rejected | whitespace, `/`, control characters, anything else |
| Length | 3 to 256 characters |

Whatever passes is stored **byte for byte as you sent it**. Nothing is lower-cased and no
separator is rewritten, so a plant tag stays a plant tag:

```text
VAL-21-PT-1034      ok, stored as sent
=K1-M3+B02          ok — an IEC 81346 designation keeps its aspect prefixes
21_PT_1234          ok
Pump-A 01           rejected: contains a space
line/3              rejected: contains a forward slash
P1                  rejected: shorter than 3 characters
```

Byte-for-byte storage is what lets you join on identifiers you already maintain. The
historian, the maintenance system and DataHub hold the same string, so a match is a string
comparison instead of a normalisation each integration has to reimplement identically,
forever.

### Layer 2 — the naming policy {#the-naming-policy}

A convention an administrator configures on top of the floor. It applies to **resources and
data sets**; enforcement sits on those write paths.

| Preset | Accepts |
| --- | --- |
| `qualified_tag` | The charset floor, plus at least 3 separator-delimited alphanumeric runs. `VAL-21-PT-1034` and `=K1-M3+B02` pass; `pump-1234` and `P-101` do not. **The shipped default, in `warn` mode.** |
| `verbatim_tag` | The charset floor and nothing more. |
| `snake_case` | `[a-z0-9_]+` only. |
| `pattern` | An administrator-supplied regular expression. |

Each policy runs in one of two modes: **reject**, where the request fails with `400` and
nothing is written, or **warn**, where the request succeeds and a finding is recorded for a
data steward. A **near-duplicate guard** runs regardless of the preset and is described
[below](#the-near-duplicate-guard).

Out of the box that means a two-part id such as `pump-1234` is **written and flagged**, not
refused, while a near duplicate is refused outright. If you are hardening an import, treat a
non-empty `warnings` array as work to do rather than noise.

Resolution is tenant-first with a per-data-set override: a data set's own naming policy wins
if it has one, otherwise the tenant's. The override **replaces** the tenant policy rather
than merging with it.

:::caution The naming policy never applies to events
Only the charset floor does. An event external id is not a name someone chose, it is the
source system's key for the subject, so the platform does not impose a convention on data you
do not own — and the policy's other rules would be meaningless there anyway, since events
deliberately share external ids.

With a `snake_case` policy active and set to reject, `client.resources().create(...)` with
`21-PT-1234` fails and `client.events().create(...)` with `21-PT-1234` succeeds. That is
correct behaviour, not a gap.
:::

## Case: compared without it, stored with it

Uniqueness on resources, data sets and time-series ignores case. Creating `val-21-pt-1034`
when `VAL-21-PT-1034` already exists is a duplicate and comes back as **`409`**, with a
message naming the id it collides with — it is the ordinary "this external id already
exists" path, not a naming-policy rejection.

Lookups ignore case for the same reason, so uniqueness and lookup agree:

```text
GET  /resources/VAL-01     ─┐
                            ├─ the same resource
GET  /resources/val-01     ─┘
```

Storage is still verbatim, so **what you read back is byte-identical to what you sent** — a
lookup by `val-01` returns an entity whose `externalId` is `VAL-01`. Compare external ids
case-insensitively in your own code if you compare them at all.

## Batches are all-or-nothing

Every endpoint that takes a list validates the **whole batch before writing anything**. One
bad item in 500 creates nothing, and the error names every offending item rather than
stopping at the first, so a rejected import is fixed in one pass.

Items in the same request are also compared against each other, not just against stored data
— sending `PUMP-01` and `pump-01` together is rejected.

## Warnings on the response

When a policy is in warn mode, the write succeeds and the envelope carries a `warnings` array
alongside `items`. It is **absent when empty**, so a client that has never looked at it sees
no change:

```json
{
  "items": [ ... ],
  "warnings": [
    {
      "index": 3,
      "externalId": "Pump-A 01",
      "policy": "naming_snake_case",
      "message": "Does not match naming policy 'snake_case'.",
      "suggestion": "pump_a_01"
    }
  ]
}
```

`index` is the item's position in the request you sent. Each warning is also persisted as a
[finding](#findings) for a data steward, so ignoring the array does not make the problem go
away quietly.

## Rejections

A naming-policy failure is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem
document:

```json
{
  "type": "https://datahub.intellistream.ai/errors/naming-policy",
  "title": "Bad Request",
  "status": 400,
  "detail": "2 of 500 external ids violate naming policy 'snake_case'. Nothing was created.",
  "violations": [
    {
      "index": 3,
      "externalId": "Pump-A 01",
      "policy": "naming_snake_case",
      "reason": "contains a space",
      "suggestion": "pump_a_01"
    }
  ]
}
```

It is **`400`, not `403`** — malformed input, not an access decision. `detail` says outright
that nothing was created, because that is the first thing you need to know before retrying.

The body reaches you through the ordinary error path in each client: `DatahubApiException`
in Java (`statusCode()` and `body()`), `DataHubException` in Python, `ResponseError` in Rust.
See [Results & errors](./client#results--errors).

| Status | Means |
| --- | --- |
| `400` | Charset floor or naming policy rejected one or more ids. Nothing was written. |
| `409` | The external id already exists, compared without case. |

## The near-duplicate guard

Always on, independent of the preset, and scoped to the **whole tenant** rather than one data
set. It fires when a new id would land beside an existing one that differs only by case or by
which separator it uses:

```text
existing:  pump_a_01
incoming:  pump-a-01     → near duplicate
incoming:  PUMP.A.01     → near duplicate
incoming:  pump_a_02     → fine
```

Its mode is `reject` by default and can be set to `warn`. Tenant scope is deliberate:
uniqueness is already tenant-wide, and two spellings of one tag cannot both be *the*
identifier for one asset even when they arrive through different data sets.

## Preflight: check before you write

```http
POST /policies/naming/check
```

Takes candidate external ids and an optional data set id, and returns the same findings the
write path would produce — **without writing anything**. It runs the same evaluator, so
there is no second set of rules to keep in step.

```json
{
  "externalIds": ["Pump-A 01", "pump_a_02"],
  "names": ["Pump A 01", "Pump A 02"],
  "dataSetId": 4471
}
```

`names` is optional and pairs with `externalIds` **by position**. Supply it when you have it:
suggestions are derived from the name first, so an entity called `Valve pressure sensors`
gets offered `valve_pressure_sensors`, where deriving from a broken id could only manage
`vps`. Either omit `names` entirely or send exactly as many as there are external ids — a
partial list is rejected rather than paired up wrongly.

Two things it is good for:

- validating an id as a user types it, rather than on submit;
- answering *"what would this policy do to the ids I already have?"* before an administrator
  turns it on.

### Suggestions {#suggestions}

Every warning and every rejection carries a `suggestion` where one can be derived — a
conforming external id you can offer as a one-click fix. It is **offered, never applied**:
the platform stopped rewriting external ids, which is the whole point of this change.

Two guarantees make it safe to wire straight into a form:

- **A suggestion always satisfies the policy it is offered for.** It is checked against the
  charset floor, the length bounds and the active preset before being returned, so applying
  one cannot bounce back with a second rejection.
- **A suggestion is never an id that is already taken** — neither one that is stored nor one
  claimed by an earlier item in the same batch.

When nothing can be derived that satisfies both, `suggestion` is absent. That is deliberate:
an honest omission beats a confident wrong answer. In particular a near-duplicate rejection
usually has no suggestion, because every variant of the same name folds to the same taken
value — the `reason` names the existing id instead, since the likeliest fix is to use it.

## Findings {#findings}

Every warning is persisted, so warn means *allowed and in the steward's queue*, not *allowed
and forgotten*.

```http
GET  /policies/findings                  # filter by policy, data set, open vs resolved
POST /policies/findings/{id}/resolve
```

Resolving is a judgement rather than a fix: the entity still breaks the policy, someone has
decided that is acceptable. A resolved finding is not reopened when the entity is edited for
unrelated reasons — only when the offending external id itself changes.

Findings are raised for resources, data sets and time series — everything whose external id
is a unique identity. Events raise none, whatever the policy says.

## Practical advice

- **Send the identifier your source system already uses.** Pre-normalising to snake_case
  still works and nothing that worked before has stopped, but it costs you the byte-for-byte
  join the platform is built around.
- **Never change an external id after the fact.** It is a promise other systems have written
  down. The platform permits it; your integrations will not forgive it.
- **Read `warnings` if you have a steward.** It is the difference between finding out now and
  finding out from a search that quietly comes back short.
- **On events, keep the subject's key.** One id, many events, in time order.
