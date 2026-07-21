# Development model

## Change sequence

1. Create or update a requirement in `specs/`.
2. Create an RFC for cross-cutting behavior or an ADR for local design.
3. Implement the smallest vertical change.
4. Add unit, property, schema, contract, scientific, or operational tests as applicable.
5. Regenerate `artifacts/traceability.json`.
6. Submit a pull request with scientific, security, data, and UX impact sections.

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
