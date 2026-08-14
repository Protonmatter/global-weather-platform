# Repository posture

`Protonmatter/global-weather-platform` is publicly viewable source under a proprietary license. Public visibility does not grant permission to copy, modify, redistribute, sublicense, or sell the software, specifications, schemas, or documentation.

## Current governance

- The repository is owned by the `Protonmatter` personal account.
- `@Protonmatter` is the enforceable CODEOWNER for every path.
- Pull requests are expected to pass the repository's quality, specification, schema, scientific, integration, lock-freshness, and operator-console checks before merge.
- Security-sensitive release construction remains on explicitly registered internal runners.

## Intended organization migration

Independent review teams such as scientific verification, data architecture, platform SRE, and product security cannot be enforced through team CODEOWNERS while the repository remains under a personal account. Before external collaboration or production operations expand, the repository should move to a GitHub organization with real teams and branch rules requiring the relevant CODEOWNER approvals.

## Secrets and deployment identifiers

Public source must not contain service credentials, provider API keys, signed URLs, internal registry credentials, or production environment values. Opaque project identifiers and source placeholders are not credentials, but they should still be treated as deployment metadata and changed only through reviewed release workflows.
