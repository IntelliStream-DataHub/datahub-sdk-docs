---
sidebar_position: 5.7
title: Policies & governance
---

# Policies & governance

A **policy** is a rule a data set is held to: read-only, field masking, a naming convention.
Each one is an instance of a policy **type**, and it is a node in the same graph as resources,
which is why the reads answer in `Policy`.

A **governance template** describes the compliance rules (retention, access restrictions,
required metadata) a data set can be held to. Templates are read-only over the API: you attach
one to a data set through that data set's policy, and DataHub then enforces it on reads and
writes.

The Java client reaches them through `client.policies()` and `client.governance()`. To offer
"which policy" when creating or re-pointing a data set,
[`datasets().policies()`](./datasets#client-coverage) is the dataset-facing view of the same
catalogue, and all three clients have it.

## Policy types {#types}

`GET /policies/types` is the catalogue of rules a policy can instantiate. Read it before
creating one: each entry's `templateId` is what a new policy names to say which rule it is.

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

Attaching a policy where its type does not allow is refused on create, over the whole batch,
rather than accepted and quietly enforcing nothing.

## Read, create, update, delete

```java
DataWrapper<Policy> some = client.policies().list(100);
DataWrapper<Policy> one = client.policies().getById(5677892L);

Policy readOnly = new Policy();
readOnly.setName("plant_oslo_read_only");    // unique
readOnly.setTemplateId(4L);                  // from listTypes()
client.policies().create(List.of(readOnly));
```

`externalId` is optional on a create, for integrations that need a stable identifier.

`update` is partial, on the same field verbs as
[`resources().update`](./resources#update): `set`, `setNull`, and `add` / `remove` for
`metadata`. Only the fields named in each entry's `update` block change.

```java
import ai.intellistream.datahub.models.forms.UpdatePolicyForm;

UpdatePolicyForm off = new UpdatePolicyForm();
off.setExternalId("plant_oslo_read_only");
off.getUpdate().getDeactivated().set(true);
client.policies().update(List.of(off));
```

:::note Omitting a field leaves it alone, and that matters for `deactivated`
The whole-object form this replaced silently re-activated a switched-off policy on any
unrelated edit, because `deactivated` was absent from the body and read as false. Send only
what you want changed.
:::

`delete` takes ids and answers `204` with no body:

```java
client.policies().delete(List.of(IdCollection.createFromExternalId("plant_oslo_read_only")));
```

## Dry-run a name against the naming policy {#naming-check}

`POST /policies/naming/check` runs the naming policy over candidate external ids and reports
what it **would** do, writing nothing. It uses the same evaluator as the write path, so the
answer cannot disagree with what a real write would do.

Two uses: telling someone their id is wrong while they are still typing it, rather than failing
the create; and answering "what would this policy do to the ids I already have" before turning
it on.

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
| `names` | Optional, aligned by position. Either omit entirely or supply exactly as many as there are ids: a length mismatch is rejected rather than silently pairing the wrong name with the wrong id. Worth supplying, because a suggestion derived from a name a human chose is better than one derived from a broken id. |
| `dataSetId` | Check against the policy governing this data set. Omit for the tenant policy. `403` when you cannot read it. |

The response is a map with one key, `findings`, which the Java client unwraps: `checkNaming`
hands you the list itself. Only non-conforming ids appear, so an empty list means every id is
fine. `PolicyFinding` is a record: `index()` (the item's position in
your batch), `externalId()`, `decision()` (`OK`, `WARNING` or `NOT_OK`), `policyExternalId()`
(`policy` on the wire), `message()` and `suggestion()`, which is null when none can be derived.
The suggestion is offered for you to accept, never applied: nothing here rewrites an external
id.

Violations that were **allowed through** and recorded are a different thing and are not
returned here. They are events, read with `events().filter` on `type = "policy_finding"`.

## Governance templates {#governance-templates}

```java
import ai.intellistream.datahub.models.GovernanceTemplateDTO;

DataWrapper<GovernanceTemplateDTO> all = client.governance().listTemplates();
DataWrapper<GovernanceTemplateDTO> one = client.governance().getTemplateById(12L);
```

`GovernanceTemplateDTO` is a record of `id()`, `externalId()`, `name()`, `description()` and
`metadata()`.

## The Java surface {#client-coverage}

| Operation | Endpoint | Java |
| --- | --- | --- |
| List policies | `GET /policies?limit=` | `policies().list` |
| List policy types | `GET /policies/types` | `policies().listTypes` |
| Get by id | `GET /policies/{policyNodeId}` | `policies().getById` |
| Create | `POST /policies/create` | `policies().create` |
| Update | `POST /policies/update` | `policies().update` |
| Delete | `POST` or `DELETE /policies/delete` | `policies().delete` |
| [Naming dry-run](#naming-check) | `POST /policies/naming/check` | `policies().checkNaming` |
| List governance templates | `GET /governance/templates` | `governance().listTemplates` |
| Get a governance template | `GET /governance/templates/{id}` | `governance().getTemplateById` |
