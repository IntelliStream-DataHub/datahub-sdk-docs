---
sidebar_position: 5.7
title: Policies & governance
---

# Policies & governance

A **policy** is a rule data is held to, and a node in the same graph as resources. Today one
kind is enforced: the [naming policy](./external-ids#the-naming-policy). The other
[types](#types) are recorded and attached, but nothing checks them yet.

A policy applies where it is [attached](#attachment): to the data sets in its `enforcedOn`, or,
attached to none, to the whole tenant.

A **governance template** is a named set of policy metadata. Templates are read-only over the
API; a policy names one through `templateId`, and the template's metadata is merged into the
policy. The policy, not the template, decides what is enforced.

The Java client reaches both through `client.policies()` and `client.governance()`.
[`datasets().policies()`](./datasets#client-coverage) lists the same catalogue from the data
set side, in all three clients.

Python and Rust have no policy service. A policy is a node, so they reach one through
[`resources`](./resources#typed-reads): a read narrowed to node type `policy` comes back as `Policy`,
and `resources.create` takes a `Policy` node, under the same `403` rule as any
[`POLICY`-labelled create](./resources#body).

## Policy types {#types}

`GET /policies/types` lists the types a policy can instantiate. Each entry carries the type's
`name`, `type` and `description`.

```java
import ai.intellistream.datahub.models.Policy;

DataWrapper<Policy> types = client.policies().listTypes();
```

| Type | Scope | What it does |
| --- | --- | --- |
| `SECURITY_POLICY` | One data set | Restricts data access or actions for security compliance. |
| `ENCRYPTION_POLICY` | One data set | Encryption requirements for stored or transmitted data. |
| `MASKING_POLICY` | One data set | Hides or obfuscates sensitive fields. |
| `IS_WRITE_PROTECTED` | One data set | Marks the data set read-only; blocks writes except delete. |
| `IS_READ_PROTECTED` | One data set | Restricts read access to authorised users. |
| `HAS_REQUIREMENT` | One data set | Marks a data set that must meet a compliance requirement. |
| `NAMING_CONVENTION` | Tenant-wide, overridable per data set | Enforces the [external-id naming convention](./external-ids#the-naming-policy) at write time. Applies to resources and data sets; events are exempt. |

Only `NAMING_CONVENTION` is enforced; the others record intent. Attaching a policy where its
type does not allow is refused on create, over the whole batch.

## Read, create, update, delete

```java
DataWrapper<Policy> some = client.policies().list(100);
DataWrapper<Policy> one = client.policies().getById(5677892L);

Policy readOnly = new Policy();
readOnly.setName("Oslo read only");
readOnly.setExternalId("plant_oslo_read_only");     // optional
readOnly.setEnforcedOn(List.of(                     // optional; leave out for tenant-wide
        IdCollection.createFromExternalId("plant_oslo")));
client.policies().create(List.of(readOnly));
```

An `externalId` you leave out is generated. `templateId` names a
[governance template](#governance-templates).

`type` is `NAMING_CONVENTION` on a naming policy and null on every other one. It is no longer
read from the policy's `name`. `type` and `value` are deprecated: still accepted on a request,
so older clients keep working, but they change nothing.

`update` is partial, on the same field verbs as
[`resources().update`](./resources#update): `set`, `setNull`, and `add` / `remove` for
`metadata`. Only the fields named in each entry's `update` block change; a field you leave out
keeps its stored value, `deactivated` included. A `templateId` that names no template is a
`400`; updating a policy that does not exist is a `404`.

```java
import ai.intellistream.datahub.models.forms.UpdatePolicyForm;

UpdatePolicyForm off = new UpdatePolicyForm();
off.setExternalId("plant_oslo_read_only");
off.getUpdate().getDeactivated().set(true);
client.policies().update(List.of(off));
```

`delete` takes ids and answers `204` with no body:

```java
client.policies().delete(List.of(IdCollection.createFromExternalId("plant_oslo_read_only")));
```

## Where a policy applies {#attachment}

`enforcedOn` lists the data sets a policy is attached to, each as an `id` and `externalId`. An
empty list means the policy is tenant-wide. It is filled on the `/policies` reads (`list`,
`getById`, and the responses of `create` and `update`); a policy read through `resources` comes
back with `enforcedOn` null, meaning not loaded, not tenant-wide.

On create, list the data sets in `enforcedOn` (by `id` or `externalId`), or name one in
`dataSetId`. On update, `enforcedOn` takes `set` (replace the list; an empty `set` makes the
policy tenant-wide), `add` and `remove`. Only the difference is applied: data sets already
attached stay as they are.

```java
UpdatePolicyForm attach = new UpdatePolicyForm();
attach.setExternalId("plant_oslo_read_only");
attach.getUpdate().getEnforcedOn()
        .add(List.of(IdCollection.createFromExternalId("plant_bergen")))
        .remove(List.of(IdCollection.createFromExternalId("plant_oslo")));
client.policies().update(List.of(attach));
```

A data set that does not exist, or a node that is not a data set, is a `400` naming the
`enforcedOn` entry; nothing is attached. A change takes effect on the next write, with no cache
delay. Two naming policies on the same data set (or two tenant-wide ones) resolve to the one with
the lowest id.

Detaching a policy, or deleting a data set a policy is attached to, is never refused as
stranding the graph: the policy is not counted as a connection.

## Dry-run a name against the naming policy {#naming-check}

`POST /policies/naming/check` runs the naming policy over candidate external ids and reports
what it would do. It writes nothing.

```java
import ai.intellistream.datahub.models.policy.NamingCheckForm;
import ai.intellistream.datahub.models.policy.PolicyFinding;

NamingCheckForm form = new NamingCheckForm();
form.setExternalIds(List.of("COM-99-PT-1034", "vps"));
form.setNames(List.of("Valve 21 PT 1034", "Valve pressure sensors"));
form.setDataSetId(12L);                      // omit for the tenant policy

List<PolicyFinding> findings = client.policies().checkNaming(form);
for (PolicyFinding finding : findings) {
    System.out.println(finding.externalId() + ": " + finding.message()
            + " (try " + finding.suggestion() + ")");
}
```

| Field | Notes |
| --- | --- |
| `externalIds` | Required, at most 1000. |
| `names` | Optional, aligned by position. Either omit it or supply exactly as many as there are ids; a length mismatch is rejected. |
| `dataSetId` | Check against the policy governing this data set. Omit for the tenant policy. `403` when you cannot read it. |

`checkNaming` unwraps the `findings` envelope and hands back the list. Only non-conforming ids
appear, so an empty list means every id is fine. `PolicyFinding` is a record: `index()` (the item's position in
your batch), `externalId()`, `decision()` (`OK`, `WARNING` or `NOT_OK`), `policyExternalId()`
(`policy` on the wire), `message()` and `suggestion()`, which is null when none can be derived.

Violations that were allowed through and recorded are events, read with `events().filter` on
`type = "policy_finding"`.

## Governance templates {#governance-templates}

```java
import ai.intellistream.datahub.models.GovernanceTemplateDTO;

DataWrapper<GovernanceTemplateDTO> all = client.governance().listTemplates();
DataWrapper<GovernanceTemplateDTO> one = client.governance().getTemplateById(12L);
```

`GovernanceTemplateDTO` is a record of `id()`, `externalId()`, `name()`, `description()` and
`metadata()`.

## What each client covers {#client-coverage}

| Operation | Java | Python | Rust |
| --- | --- | --- | --- |
| List policies (`GET /policies?limit=`) | `policies().list` | — | — |
| List policy types (`GET /policies/types`) | `policies().listTypes` | — | — |
| Get by id (`GET /policies/{policyNodeId}`) | `policies().getById` | — | — |
| Create (`POST /policies/create`) | `policies().create` | — | — |
| Update (`POST /policies/update`) | `policies().update` | — | — |
| Delete (`POST` or `DELETE /policies/delete`) | `policies().delete` | — | — |
| [Naming dry-run](#naming-check) (`POST /policies/naming/check`) | `policies().checkNaming` | — | — |
| List governance templates (`GET /governance/templates`) | `governance().listTemplates` | — | — |
| Get a governance template (`GET /governance/templates/{id}`) | `governance().getTemplateById` | — | — |
