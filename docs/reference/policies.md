---
sidebar_position: 5.7
title: Policies & governance
---

# Policies & governance

A **policy** is a rule a data set is held to: read-only, field masking, a naming convention.
Each one is an instance of a policy **type**, and each is a node in the same graph as
resources.

A **governance template** describes compliance rules (retention, access restrictions, required
metadata). Templates are read-only over the API; a policy names one through `templateId`, and
the template's metadata is merged into the policy.

The Java client reaches both through `client.policies()` and `client.governance()`.
[`datasets().policies()`](./datasets#client-coverage) lists the same catalogue from the data
set side, in all three clients.

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

## Read, create, update, delete

```java
DataWrapper<Policy> some = client.policies().list(100);
DataWrapper<Policy> one = client.policies().getById(5677892L);

Policy readOnly = new Policy();
readOnly.setName("IS_WRITE_PROTECTED");             // the type it instantiates
readOnly.setExternalId("plant_oslo_read_only");     // optional
client.policies().create(List.of(readOnly));
```

A policy's `type` is read back from its `name`, so name it after the type. An `externalId` you
leave out is generated. `templateId` names a [governance template](#governance-templates).

`update` is partial, on the same field verbs as
[`resources().update`](./resources#update): `set`, `setNull`, and `add` / `remove` for
`metadata`. Only the fields named in each entry's `update` block change; a field you leave out
keeps its stored value, `deactivated` included.

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
