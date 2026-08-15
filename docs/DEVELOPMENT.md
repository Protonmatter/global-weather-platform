# Development model

## Change sequence

1. Create or update a requirement in `specs/`.
2. Create an RFC for cross-cutting behavior or an ADR for local design.
3. Implement the smallest vertical change.
4. Add unit, property, schema, contract, scientific, or operational tests as applicable.
5. Regenerate `artifacts/traceability.json`.
6. Run `make dependency-policy` and the applicable end-to-end lane.
7. Submit a pull request with scientific, security, data, and UX impact sections.

## Delivery gates

The reusable continuous-integration workflow fans out specification,
dependency-lock, Python, operator-console, schema, scientific, integration, and
process-boundary end-to-end checks. Continuous delivery cannot construct a
release image until that entire fan-out passes for the same revision.

Dependency updates follow the same sequence as application changes: update the
bounded manifest, regenerate the committed lock with the pinned compiler, keep
the runtime pins explicit, update affected requirements when compatibility
changes, and run the complete gate. Automated major upgrades are intentionally
disabled so they cannot bypass specification review.

## Pull-request evidence

A pull request that changes forecast semantics must include:

- affected requirement IDs;
- baseline behavior;
- candidate behavior;
- evaluation period and data version;
- primary score and confidence interval;
- predeclared slices;
- known regressions;
- rollback unit.

## Reproducibility classes

- **Bitwise reproducible:** identical output bytes on the declared platform.
- **Numerically reproducible:** values remain within specified absolute and relative tolerances.
- **Scientifically reproducible:** verification distributions and conclusions remain equivalent.

The required class must be declared by each model or computation specification.
