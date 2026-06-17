# Upgrade notes

How to keep the platform upgrade-safe and how to perform the recurring updates the product
needs.

## Odoo version upgrades

The addons target **Odoo 19 Community** and follow upgrade-safe rules:

- **Never edit Odoo core.** All customisation lives in namespaced `custom_*` addons. If a
  core change ever seems unavoidable it must be isolated in a documented `patches/` layer
  with a justification — there is no such layer today, which is the goal.
- **Extend, don't replace.** Addons inherit native models (`crm.lead`, `account.move`,
  `hr.employee`, `sale.order`, …) via `_inherit` rather than recreating them, so native
  upgrade scripts continue to apply.
- **Pin the Odoo ref.** CI checks out `odoo/odoo@19.0`. When moving to 20+, bump that ref
  on a branch and run the full suite before merging.

### Upgrade procedure
1. Branch. Bump the Odoo ref in `.github/workflows/ci.yml` and the `Dockerfile` base.
2. `docker compose build odoo` and run `--test-enable -u all` against a copy of production
   data in a scratch DB.
3. Fix deprecations surfaced by `pylint-odoo` and the test run (view arch attributes,
   removed ORM kwargs, renamed fields).
4. Run the full test suite (`make test`, the gateway tests, and `tests/e2e` against a live
   stack). Tag only on green.
5. Take a backup, then upgrade production with `-u all` during a maintenance window.

## Schema migrations within a version

Use Odoo's standard `migrations/<version>/{pre,post}-*.py` per addon for data migrations.
Bump the addon `version` in its `__manifest__.py` so Odoo runs the scripts on `-u`.

## Yearly payroll rules update (recurring)

`custom_payroll_nl` uses a **versioned rules engine** (`hr.payroll.rule.version`), so a new
tax year is a **data** change, not a code change: add a new version record with the year's
parameters. The engine warns when parameters are missing/outdated. No migration required —
see `payroll_nl.md`.

## AI provider / model changes

Switching provider or model is config only (`DEFAULT_PROVIDER`, `DEFAULT_MODEL`,
`EMBEDDING_*`). If you change the **embedding model or its dimensions**, existing pgvector
rows become incompatible — re-ingest documents (delete + `/rag/ingest`) so vectors match
the new dimensionality. Keep `EMBEDDING_DIMENSIONS` aligned with the model.

## Dependency upgrades

Service dependencies are pinned in each `services/*/requirements.txt` and
`support_app/package.json`. Bump deliberately, rebuild images, and rely on CI + the
gateway tests to catch breakage. The pre-commit hooks (ruff, black, pylint-odoo,
secret-scan) gate local commits.

## Breaking-change log

Record any change that alters stored data shape, public endpoints, or required env vars in
`docs/devlog.md` under the milestone where it lands, so client instances can be migrated
safely.
