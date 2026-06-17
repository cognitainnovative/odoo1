# Cognita Platform — Consolidated Sign-Off (M1–M16)
**Odoo 19 Community · Database: tf_v19com · 18 custom modules**

Status at sign-off: **Full suite 806 tests, 0 failed, 0 errors.** Security review
complete. Consolidated UI pass (positive/negative/risky/brutal) complete. All
findings fixed and re-verified.

---

## 1. Scope

18 custom modules delivered across milestones M1–M16, extending Odoo 19 Community
into a branded, multi-company, subscription-gated ERP/CRM platform with AI features.

| # | Module | Milestone area |
|---|--------|----------------|
| 1 | custom_theme | Branding, platform home/dashboard |
| 2 | custom_platform_security | RBAC, API tokens, audit log, GDPR |
| 3 | custom_subscription_modules | Per-company package gating |
| 4 | custom_ai_core | AI provider abstraction, RAG, redaction, audit |
| 5 | custom_crm_core | Leads, pipeline, custom fields, campaigns |
| 6 | custom_quote_signing | Quote e-signing + audit |
| 7 | custom_accounting_basic | Bank import, reconciliation, recurring invoices |
| 8 | custom_planning | Job scheduling, calendar, reminders |
| 9 | custom_inventory | Stock extensions, bundles, alerts |
| 10 | custom_rental | Rental orders, availability, deposits |
| 11 | custom_hrm | Employees, leave, sick-leave (privacy-safe), portal |
| 12 | custom_payroll_nl | NL payroll engine, payslips |
| 13 | custom_accounting_advanced | Reports, accruals, period lock, fixed assets, budgets |
| 14 | custom_ai_chatbot | Website chat, RAG, consent, escalation |
| 15 | custom_helpdesk + custom_email_ai | Tickets, SLA, portal, mailbox AI |
| 16 | custom_whatsapp_social + custom_ai_voice | WhatsApp/social + voice (consent-gated) |

(M16 = cross-cutting hardening, security review, dashboards, docs, full-suite gate.)

---

## 2. Per-milestone sign-off

| Milestone | Deliverable | Tests | Status |
|-----------|-------------|-------|--------|
| M1 | Theme / subscription / security | green | ✅ Signed off |
| M2 | AI core (providers, RAG, redaction, audit) | green | ✅ |
| M3 | CRM core | green | ✅ |
| M4 | Quote signing | green | ✅ |
| M5 | Accounting basic + planning | green | ✅ |
| M6 | Planning | green | ✅ |
| M7 | Inventory | green | ✅ |
| M8 | Rental | green | ✅ |
| M9 | HRM (privacy-critical) | green | ✅ |
| M10 | Payroll NL | green | ✅ |
| M11 | Accounting advanced | green | ✅ |
| M12 | AI chatbot | green | ✅ |
| M13 | Helpdesk + Email AI | green | ✅ |
| M14 | WhatsApp + Social | green | ✅ |
| M15 | AI Voice | green | ✅ |
| M16 | Hardening / security / docs / full-suite | 806 green | ✅ |

---

## 3. Test status

- **Full suite: 806 tests, 0 failed, 0 errors** (all 18 modules upgraded + tested
  together in one CI run — the spec's release gate).
- Re-run command: `run_full_suite.sh`.
- The full-suite run surfaced and resolved cross-test isolation issues that
  per-module runs hid (subscription registry-cache rollback; deliberate-duplicate
  constraint tests without savepoints). All fixed.

---

## 4. Findings log — brutal pass + UI pass (16 total, all fixed)

### Code-review / brutal automated pass (9)
Real bugs (6):
1. M5 — bank parser read US-format amounts as €0 (dropped transactions).
2. M6 — rescheduled job didn't re-arm reminder (cron never re-notified).
3. M2 — credit card mislabeled as phone in PII redaction (pattern order).
4. M10 — company-car bijtelling inflated cash net pay (taxed-not-paid fix).
5. M11 — accrual reversal built an unbalanced 1-line move that could never post.
6. M13 — helpdesk portal controller never imported (all portal routes 404'd).

Compliance/safety gaps (3) — all "consent/flag recorded but never enforced":
7. M12 — high-risk medical/financial questions not auto-escalated (bot answered).
8. M14 — WhatsApp send ignored opt-in (policy violation; reply-window aware fix).
9. M15 — call recording: silent recording + false consent records (two-party
   consent disclosure + callback consent check added).

### Consolidated UI pass (7)
10. M12 — Live Chat kanban crash ("Missing 'card' template"; Odoo-19 template name).
11. M3 — CRM custom-field section: missing field selector + no definition menu.
12. General — invalid date ranges (end before start) not rejected; added
    @api.constrains to rental, sick-leave, planning, campaign, budget, accrual.
13. M9 — website-created sick leaves not shown on /my/leaves (model mismatch).
14. M10 — payroll run executed with no employee data (now blocked with error).
15. M12 — chat links rendered as plain text (now safe clickable links).
16. M1 — Home menu inert + dashboard cards not clickable + duplicate "New Company"
    name on company create (root menu→child + action buttons + unique placeholder).

**Pattern (most important takeaway):** original green test suites hid every one of
these. Three compliance gaps shared one root cause — consent was *recorded* but
never *enforced* at the decision point. Only adversarial "does it actually block?"
testing caught them. UI-layer bugs (404 route, kanban template, missing menus)
were invisible to model tests and only the manual UI pass surfaced them.

---

## 5. Security review (M16)

- **Secret storage — PASS.** AI keys + email passwords are encrypted
  (Fernet / ir.config_parameter), not plaintext. API tokens hashed.
- **Company isolation — gap found & fixed.** Added company record rules to
  persistent business/PII models (email mailbox/outbox/finance-task, recurring
  invoice template, accounting audit log, BV annual accounts, helpdesk team).
  Two invalid candidate rules dropped after verifying the models lack company_id.
- **RBAC — PASS.** 7 custom groups, ~206 ACL rules, 3 enforcement layers
  (ACL + record rules + model guards). HR payslip/sick-leave own-record isolation
  verified via with_user tests + cross-company isolation test.
- **Consent/approval enforcement — PASS** (after M12/M14/M15 fixes).
- **Audit logging — PASS** (immutable, company-scoped).
- **GDPR — PASS** (export, anonymise, retention purge).

---

## 6. Recurring environment/schema issues resolved (NOT module defects)

- **tf_v19com partner column drift** (autopost_bills / group_rfq / group_on):
  permanently resolved via SET DEFAULT; quiet across 7 combined-upgrade cycles.
- **Asia/Calcutta timezone:** stale stock-Odoo demo data on this DB; corrected in
  data. Permanent fix = reinstall server tzdata so the alias resolves.
- **Stale addons copy (traefik vs traefix_1):** ensure Odoo loads from a single
  addons path so a stale copy cannot shadow fixed code.
- **Invoicing vs full Accounting:** bank-import/reconciliation features require the
  full Accounting app (not Invoicing-only).

---

## 7. Documented decisions / known limitations (by design)

- **Chatbot answer quality** is mock until a real AI provider API key is configured.
- **Platform dashboard cards** are clickable launchers (open the module), not
  live-KPI tiles. Live figures would be additional work.
- **Payroll** does NOT auto-file with the Belastingdienst — it marks runs
  "Exported" for manual filing (correct; avoids unauthorized government submission).
- **External-provider credentials** (Meta WhatsApp app review, X API tier, Twilio,
  Deepgram, ElevenLabs) run in mock/sandbox until provisioned.
- **Multi-company SETUP-data isolation** (provider/prompt/chat configs) left to
  client decision; per-user business data is isolated.

---

## 8. Deliverables (in /mnt/user-data/outputs/)

- 18 `*_fixed.zip` module packages (latest, all fixes applied).
- `CHANGES_M2`…`CHANGES_M16` + `CHANGES_UI_FINDINGS.md` (per-area change logs).
- `M1_SIGNOFF`…`M5_SIGNOFF.md` (early per-milestone sign-offs).
- `BRUTAL_TEST_TRACKER.md` (full findings + UI checklist log).
- `docs/`: RBAC_MATRIX, SECURITY_REVIEW, onboarding_client, backup_restore,
  CRITICAL_FLOWS, UI_TEST_CHECKLIST, UI_SCENARIO_TESTS.
- `run_full_suite.sh` (CI gate command).
- This document: `PLATFORM_SIGNOFF_M1_M16.md`.

---

## 9. Sign-off statement

All 16 milestones are delivered. The full automated suite (806 tests) passes with
zero failures/errors across all 18 modules in one run. The security review is
complete with gaps found and fixed. The consolidated UI pass is complete with all
16 findings fixed and re-verified. Recurring issues encountered were environment/
data conditions, not module defects, and are documented with resolutions.

**Outstanding before production go-live (operational, not code):**
- [ ] Confirm single addons path (no stale shadow copy).
- [ ] Permanent tzdata fix on the server (optional but recommended).
- [ ] Configure real AI/provider credentials where live behavior is required.
- [ ] Execute one backup/restore drill per backup_restore.md.
- [ ] Decide multi-company SETUP-data isolation (if multi-company in production).

Prepared as the M1–M16 release record.
