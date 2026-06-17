# Brutal Testing + UI-Tracker (all milestones)

## Brutal automated tests — STATUS
| Module | Existing | Brutal added | Real bug caught by brutal |
|---|---|---|---|
| M1 custom_platform_security | 7 | (pending eval) | — |
| M1 custom_theme | 8 | — | — |
| M1 custom_subscription_modules | 21 | (pending eval) | — |
| M2 custom_ai_core | 36 | +12 (redaction/render) | YES — card mislabeled as phone (ordering) |
| M3 custom_crm_core | 26 | (writing next) | TBD |
| M4 custom_quote_signing | 42 | (already heavy; eval) | — |
| M5 custom_accounting_basic | 99 | +33 (done earlier) | YES — US amount parser -> 0 |
| M6 custom_planning | 35 | +18 (reminder/signoff/etc) | YES — reschedule no reminder re-arm |

## Bugs fixed this brutal pass
- M6: reschedule didn't re-arm reminder_sent (cron never re-reminds) — FIXED + test
- M2: credit card redacted as [PHONE-REDACTED] (pattern order) — FIXED + test

## NEEDS UI TESTING (deferred to one consolidated pass at the end)
### M6 custom_planning
- [ ] Calendar + kanban views render; drag card between stages
- [ ] Completion report prints a REAL PDF (report schema was fixed in M5)
- [ ] "Mobile-friendly employee view" — SPEC names it; code only has standard
      kanban/list. VERIFY it exists or flag as deliverable gap.
- [ ] Reschedule in UI re-arms reminder (now fixed in code)
- [ ] Calendar with all-day / no-date jobs (edge render)

### M5 custom_accounting_basic (from earlier — still open)
- [ ] 5 untested action buttons (suggest/confirm AI match, reminder, payment link, extract review)
- [ ] Real scanned image-only PDF OCR
- [ ] CSV export downloads + opens
- [ ] Bank reconciliation EFFECT (Confirm Match is suggestion-only — KNOWN GAP)

### M3 custom_crm_core
- [ ] Dashboards (8) render empty + as non-admin
- [ ] Public /api/leads endpoint behaviour

### M2 custom_ai_core
- [ ] (mostly backend; covered by shell earlier)

### M1
- [ ] (UI verified earlier in M1 pass)

## Combined run #1 (273 tests): 1 failed, 2 errors — ALL pre-existing, none in brutal suites
- FAIL test_external_blocked_raises (ai_core): mutated seed data — FIXED (self-contained test)
- ERROR x2 company-isolation (ai_core): autopost_bills DB default missing — ENVIRONMENT, run -u account
- My new brutal suites (planning/ai/crm): ALL PASSED (no failures in them)

## COMBINED RUN — FINAL: 273 tests, 0 failed, 0 errors ✓
All five interlocking modules + brutal suites green together (cross-milestone
regression proof). Environment fixed: autopost_bills DEFAULT false on tf_v19com.

### Total brutal bugs caught & fixed this pass (3):
1. M6 planning — reschedule didn't re-arm reminder
2. M2 ai_core — credit card mislabeled [PHONE-REDACTED] (pattern order)
3. (test-quality) ai_core external-blocked test: seed-data fragility + uniqueness

### M1 brutal eval — DECISION
M1 (security/subscription/theme) reviewed + UI-verified back in M1 sign-off;
security has token/GDPR/audit tests; subscription has 21 tests. Low marginal
value from more brutal tests here vs the money/PII paths already covered. 
Recommend: no additional M1 brutal suite (diminishing returns). Re-evaluate only
if a specific M1 risk surfaces.

## AUTOMATED TESTING: COMPLETE ✓
Next phase: ONE consolidated UI pass (checklist below).

## M7 custom_inventory — brutal suite added (~13 tests)
Run #1: 3 errors, all MY test bugs (zero-quant API, invalid event_type) — fixed.
Module code SOUND: insufficient-stock/double-deduct/bundle probes all passed.
NEEDS UI: dashboards (low stock/fast-movers/stock value/reserved/oos/warehouse),
  count workflow, PO receipt, reorder-rule trigger, barcode/SKU, stock valuation report.

## M7 COMBINED RUN — FINAL: 328 tests, 0 failed, 0 errors ✓
All 7 modules (M1-M7) green together. M7 inventory brutal suite passing.
Cross-milestone regression: clean (M7 didn't disturb M1-M6).

### tf_v19com schema repairs (environment, NOT code) — done this session:
res_partner had 3 stock-Odoo columns drifted to NOT-NULL-without-default
(partial-upgrade artifacts), each surfacing as new deps pulled them in:
- autopost_bills (boolean, from account) — SET DEFAULT false
- group_rfq (boolean, from purchase) — SET DEFAULT false + DROP NOT NULL
- group_on (varchar, from purchase/mail) — DROP NOT NULL
All now match clean-Odoo behaviour. No more partner-column landmines (verified:
0 rows in NOT-NULL-no-default query).

### M7 brutal findings: NONE in module code (3 errors were my test bugs, fixed).
Auto-deduction insufficient-stock/double-deduct probes PASSED — logic sound.
Noted (not a bug): broad except in _platform_auto_deduct_stock = observability gap.

### M7 NEEDS UI (added to consolidated checklist):
- Dashboards: low stock / fast-movers / stock value / reserved / out-of-stock / warehouse overview
- Count workflow, PO receipt, reorder-rule trigger, barcode/SKU scan, stock valuation report
- Auto-deduction config toggle in Settings UI (sale/invoice/delivery)

## M8 custom_rental — brutal suite added (~16 tests). Run: 72 tests, 0 failed, 0 errors ✓
Module SOUND — brutal probes found NO real bug (clean code review confirmed):
- overbooking blocked at exact unit boundary (1/2/3 units, non-overlap, cancel-frees)
- final-amount math with damage+late+deposit deduction (TEST GATE) correct
- late-fee day calc (on-time/multi-day/early) correct
- deposit deduction capped at deposit_amount; sign/deposit gates enforced

### M8 NEEDS UI (added to consolidated checklist):
- Availability CALENDAR view render
- Dashboard: active/overdue/upcoming returns, revenue, utilization, damaged, best products, customer rental value
- Full lifecycle click-through (quote→reserve→sign→deposit→verify→pickup→return→inspect→damage→invoice→deposit release)
- ID/KVK verification record UI (status/expiry/risk flag/retention)
- Discount tier auto-assignment by annual spend + manual override + approval-above-threshold
- Recurring rental billing

## M8 COMBINED RUN — FINAL: 400 tests, 0 failed, 0 errors ✓
All 8 modules (M1-M8) green together. M8 rental brutal suite passing.

### group_on PERMANENT fix (root-caused properly this time):
Traced via ir_model_fields: group_on is owned by purchase_stock (stock Odoo),
declared required=True but with NO default value — so any partner created
without explicitly setting it failed NOT NULL. -u purchase_stock did NOT fix it
(no default to restore). The bare DROP NOT NULL kept getting reverted because the
registry still said required=True, so every -u re-applied it.
PERMANENT FIX: UPDATE ir_model_fields SET required=false WHERE name='group_on'
(+ ALTER COLUMN DROP NOT NULL). Now survives upgrades. This was the real
"code/registry-level" fix, not a DB band-aid.

LESSON: the autopost_bills/group_rfq/group_on family were registry-level
required-without-default fields. group_on recurred because only it was also
required=True in the registry; the registry UPDATE is what makes it stick.

## AUTOMATED BRUTAL PASS: M1-M8 COMPLETE ✓ (400 tests green)

## M9 COMBINED RUN — FINAL: 439 tests, 0 failed, 0 errors ✓
All 9 modules (M1-M9) green together. M9 HRM brutal suite passing.

### group_on ROOT CAUSE — finally resolved permanently (proven survives upgrade):
group_on is a REAL purchase_stock selection field on res.partner (confirmed via
i18n/.po translation entries: group_on__default, __1..__7). NOT an orphan.
On tf_v19com it lost its column DEFAULT (partial-upgrade drift), leaving it
NOT NULL with no default -> any partner insert omitting it failed.

WHY IT ALONE RECURRED: the 3 drifted partner columns were autopost_bills,
group_rfq (boolean) and group_on (selection). We gave the booleans SET DEFAULT
false (self-healing). group_on only ever got DROP NOT NULL, never a default — so
each module install re-synced the field, re-applied NOT NULL, and it failed again
because it had no default. It was the ONLY one missing a default.

PERMANENT FIX: ALTER COLUMN group_on SET DEFAULT 'default' (its real Odoo default
per the selection keys) + backfill nulls. PROVEN: survived a combined -u upgrade
(the operation that used to revert it); column_default now 'default'.

LESSON for M10+: if a NEW dependency pulls a NOT-NULL-without-default partner
column, the fix is SET DEFAULT <correct value> (self-healing), not just DROP
NOT NULL. For selection/char fields find the real default; for booleans use false.

## M9 NEEDS UI (added to consolidated checklist):
- Employee self-service portal: /my/profile, /my/leaves, /my/payslips,
  /my/documents (upload), /my/planning (calendar), /my/sick-leave/report
- CRITICAL privacy UI check: log in as Employee B, confirm cannot see Employee A's
  payslips/sick-leave/documents via the portal (the .sudo() controller surface)
- Leave request -> manager+HR approval -> balance update (calendar)
- Sick-leave report flow + manager/HR notification (no medical data shown)
- Onboarding/offboarding checklists; contract/probation/cert-expiry reminders (cron)

## AUTOMATED BRUTAL PASS: M1-M9 COMPLETE ✓ (439 tests green)

## M10 COMBINED RUN — FINAL: 494 tests, 0 failed, 0 errors ✓
All 10 modules (M1-M10) green together. M10 payroll brutal suite passing.
group_on did NOT recur — survived 2 consecutive combined-upgrade cycles (M9+M10).
The SET DEFAULT 'default' fix is CONFIRMED permanent (self-healing column).

### M10 REAL BUG caught by brutal pass:
custom_payroll_nl — bijtelling (company-car taxable benefit) was inflating cash
NET pay: employee with €40k car netted €391/mo MORE than without (backwards).
Bijtelling must raise the tax base but NOT be paid as cash. FIXED: subtract
bijtelling from net. Now nets ~€342/mo LESS with a car (correct). Existing tests
checked taxable_gross + tax (correct) but never net-with-car -> bug shipped green.

### Legal blocker verified honest: code marks filing as export-only, explicit
notice it does NOT submit to Belastingdienst. No compliance faking. Good.

### M10 NEEDS UI (added to consolidated checklist):
- Payroll run -> payslip draft -> approval -> secure portal publication
- Payslip PDF (gross components/deductions/employer contrib/net/holiday/YTD)
- Role isolation: payroll/HR see all, employee sees ONLY own payslips (portal)
- Versioned rule parameters UI; manual override-with-reason + warning if params missing
- Export for accountant + export for payroll provider (CSV download)
- Payroll journal entry posting; wage-cost/employer-cost reports

## BRUTAL BUGS CAUGHT ACROSS WHOLE PASS (running total):
- M5 US amount parser -> 0 (bank import dropped transactions)
- M6 reschedule didn't re-arm reminder
- M2 credit card mislabeled [PHONE-REDACTED] (pattern order)
- M10 bijtelling inflated net pay (company-car overpayment)
M7, M8, M9 brutal-probed, no real code bug (sound).

## AUTOMATED BRUTAL PASS: M1-M10 COMPLETE ✓ (494 tests green)

## M11 custom_accounting_advanced — brutal suite added (~14 tests). M11 alone: 77/77 ✓
### M11 REAL BUG caught by brutal/gate pass:
account_accrual.action_reverse() created an UNBALANCED journal entry (one debit
line, no credit) -> account.move.create always failed in _check_balanced -> the
reversal crashed and the auto-reverse cron never advanced state. A reversal that
could NEVER post. FIXED: balanced two-line entry (debit accrual account, credit
journal default account as counterpart). Model lacks a dedicated counterpart
field (noted limitation). This is a core double-entry correctness bug on the
"reversal correction path" test gate.

### Test-mechanics learnings (Odoo 19):
- _check_balanced now fires at account.move.create(), not just post() -> tests
  that build an unbalanced move must wrap CREATE in assertRaises+savepoint.
- self.assertRaises((A, B)) TUPLE breaks Odoo's _assertRaises (issubclass on
  tuple) -> use a single exception class.
- Period lock: fiscalyear_lock_date guards MODIFYING entries in a locked period
  (button_cancel raises); admin CAN post into a locked period (soft guard). Test
  the modification block, not admin posting.

### M11 NEEDS UI (added to consolidated checklist):
- Reports render: balance sheet, P&L, trial balance, GL, aged AR/AP, VAT, cash flow
- Fixed-asset depreciation schedule view; accrual/prepayment/provision entries
- BV annual accounts package (draft -> accountant review -> PDF/Word export)
- Period lock UI + admin override-with-reason; audit-file export (tax-audit validity)
- Budget vs actual; cost centre / department / project dimensions on entries
- Invoice -> journal -> payment trace; immutable audit metadata on entries

## BRUTAL BUGS CAUGHT (running total): M5 US parser, M6 reminder re-arm,
## M2 card redaction, M10 bijtelling net, M11 accrual unbalanced reversal. (5 real bugs)

## M11 COMBINED RUN — FINAL: 571 tests, 0 failed, 0 errors ✓
All 11 modules (M1-M11) green together. group_on quiet (3rd consecutive
combined-upgrade cycle — SET DEFAULT 'default' conclusively permanent).

## ============================================================
## AUTOMATED BRUTAL PASS: M1-M11 COMPLETE ✓ (571 tests green)
## ============================================================
## 5 REAL bugs caught (all missed by original green suites):
##   M5  US bank amount parser -> €0 (dropped transactions)
##   M6  reschedule didn't re-arm reminder
##   M2  credit card mislabeled [PHONE-REDACTED]
##   M10 bijtelling inflated net pay (company-car overpayment)
##   M11 accrual reversal unbalanced (could never post)
## M7, M8, M9 brutal-probed, sound. tf_v19com schema drift fully resolved.
##
## REMAINING WORK:
## 1. CONSOLIDATED UI PASS (M3-M11) — the main outstanding risk. Checklist above.
## 2. Sign-off docs for M6-M11 (M1-M5 done).
## 3. Future milestones still in uploads: ai_chatbot, ai_voice, email_ai,
##    helpdesk, whatsapp_social.

## M12 custom_ai_chatbot — brutal suite added (~13 tests). M12 alone: 52/52 ✓
### M12 REAL GAP caught by code review + brutal pass:
high_risk escalation (medical/financial) was DEFINED but never auto-detected.
process_message checked trigger words (legal covered), human-request, frustration,
low-confidence — but NO medical/financial detection. A visitor asking for medical
or financial advice got an AI answer instead of human routing (liability: bot
giving unlicensed advice). FIXED: added HIGH_RISK_KEYWORDS, wired into
process_message before the RAG call. Brutal tests verify medical/financial
escalate but ordinary product questions do not.

### Consent gating verified SOUND (GDPR): no tracking without consent; revoke
stops tracking immediately; re-consent resumes. transcript->lead link works.

### M12 NEEDS UI (added to consolidated checklist):
- Website chat widget: greeting, RAG cited answers, lead capture, product suggestions,
  language detection, transcript, sentiment
- Consent banner gates tracking (no page-view recording pre-consent)
- React employee support app: live queue, accept/transfer, canned + AI-suggested
  replies, customer/deal context, mark resolved, create follow-up/quote/deal
- Escalation routing by availability/skill; browser push / email / WhatsApp notifications
- Public chat controller endpoint security (untrusted visitor input)

## BRUTAL FINDINGS (running total): 5 real bugs (M5,M6,M2,M10,M11) +
## 1 compliance gap (M12 high-risk escalation). M7,M8,M9 sound.

## M12 COMBINED RUN — FINAL: 623 tests, 0 failed, 0 errors ✓
All 12 modules (M1-M12) green together. group_on quiet (4th cycle).
AUTOMATED BRUTAL PASS: M1-M12 COMPLETE (623 tests green).
Findings: 5 real bugs (M5 parser, M6 reminder, M2 redaction, M10 bijtelling,
M11 accrual reversal) + 1 compliance gap (M12 high-risk escalation). All fixed.

## M13 custom_helpdesk + custom_email_ai — brutal suites added (~16 tests). M13 alone: 73/73 ✓
### M13 REAL BUG caught (helpdesk): portal controller never loaded (404 trap)
Top-level __init__.py only imported models, not controllers — so /my/tickets,
/helpdesk/ticket/<id> etc. would 404. Customer portal is a deliverable. FIXED:
__init__.py imports controllers. (Same class as M3 trap.)

### email_ai never-auto-send invariant verified SOUND (critical safety property):
new drafts pending; action_send raises unless approved; auto-send inert unless
admin enabled AND category matches. Adversarially brutal-tested — holds.

### M13 NEEDS UI (added to consolidated checklist):
- Helpdesk: ticket lifecycle, SLA dashboard/warnings/escalation, skill routing,
  AI summarize/suggest/draft (approval-gated), customer portal (/my/tickets — now fixed)
- email_ai: mailbox connect (IMAP/SMTP/Graph), import, classify->ticket/lead/finance,
  AI draft -> pending outbox -> review/edit(reason stored)/approve -> send
  pending-outbox state machine; limited auto-send ONLY after explicit admin config

## M13 COMBINED RUN — FINAL: 696 tests, 0 failed, 0 errors ✓
All 13 modules (M1-M13) green together. group_on quiet (5th cycle).
AUTOMATED BRUTAL PASS: M1-M13 COMPLETE (696 tests green).
Findings total: 6 real bugs (M5,M6,M2,M10,M11,M13-portal) + 1 compliance gap
(M12 high-risk). M7,M8,M9 sound. tf_v19com schema drift permanently resolved.
Remaining modules in uploads: custom_ai_voice, custom_whatsapp_social.
REMAINING WORK: consolidated UI pass (M3-M13); sign-off docs (M6-M13).

## M14 custom_whatsapp_social — brutal suite added (~13 tests). M14 alone: 39/39 ✓
### M14 REAL COMPLIANCE GAP caught (WhatsApp): send ignored opt-in/consent
opt_in recorded but never checked before sending — action_approve_and_send would
message contacts who hadn't opted in (WhatsApp policy violation: number bans).
FIXED: consent gate requiring opt_in EXCEPT replies to inbound (24h service
window). Cold outbound without opt-in now blocked; inbound reply allowed.

### Verified SOUND: WhatsApp approval gate; provider defaults to mock (no live
API per spec); social-post approval-before-publish/schedule; webhook imported.

### M14 NEEDS UI (added to consolidated checklist):
- WhatsApp inbox: inbound webhook -> contact link -> AI draft -> approval -> send (mock)
- consent/opt-in flow; handoff to agent; provider templates; media
- Social inbox: comments/mentions -> ticket/lead, AI reply draft + approval, sentiment
- Post planning: content calendar, AI-generated posts, approval, scheduled publishing
  (mock), topic calendar; scheduled-post state machine in UI
- Meta/X external approval items are sandbox/mock (flagged — request creds when live)

## ================================================================
## M14 COMBINED RUN — FINAL: 735 tests, 0 failed, 0 errors ✓
## AUTOMATED BRUTAL PASS: M1-M14 COMPLETE — FULL BUILD GREEN
## ================================================================
All 14 modules green together. group_on quiet (6th cycle — permanently fixed).

### REAL FINDINGS across the whole brutal pass (7 total, all fixed):
1. M5  bank parser parsed US amounts as €0 (dropped transactions)
2. M6  reschedule didn't re-arm reminder (cron never re-notified)
3. M2  credit card mislabeled [PHONE-REDACTED] (redaction pattern order)
4. M10 bijtelling inflated net pay (company-car overpayment)
5. M11 accrual reversal unbalanced (could never post)
6. M13 helpdesk portal controller never loaded (404 on customer portal)
7. M12 high-risk escalation not auto-detected (bot answered medical/financial)
   + M14 WhatsApp send ignored opt-in/consent (policy violation)
M7, M8, M9 brutal-probed, sound. tf_v19com schema drift (autopost_bills/
group_rfq/group_on) permanently resolved.

### PATTERN NOTE: original green suites hid every one of these. Several were
"data recorded but never enforced" (M12 high-risk, M14 opt-in) — brutal "does it
actually block?" tests surfaced them.

## REMAINING WORK (no more build milestones — uploads exhausted):
1. CONSOLIDATED UI PASS (M3-M14, ~12 modules) — the main remaining risk.
   M13 portal-404 proved UI/integration bugs are invisible to model tests.
2. Sign-off docs (M6-M14; M1-M5 done).

## M15 custom_ai_voice — brutal suite added (~13 tests). M15 alone: 33/33 ✓
### M15 REAL LEGAL BUG caught: recording-consent logic inverted (highest-stakes)
- Recording NOTICE only given in two-party jurisdictions -> default single-party
  config recorded SILENTLY with no notice.
- recording_consent_given set unconditionally when recording enabled (false
  consent record even with no notice). 3rd "recorded-but-not-enforced" instance.
- recording_callback stored URL with no consent check.
FIXED: notice always delivered when recording enabled+consent required; two-party
gets explicit all-party disclosure; consent marked only after notice; callback
refuses to store URL without consent (defense in depth). Real wiretapping-statute
exposure in two-party states.

### Verified SOUND: providers/STT/TTS default mock (no live API per spec);
structured sentiment labels + peak tracking; escalation threshold configurable, fires once.

### M15 NEEDS UI (added to consolidated checklist):
- Inbound call mock -> STT -> RAG -> TTS loop; call-flow builder
- Recording CONSENT flow in a 2-party-consent config (verify notice + explicit consent)
- Escalation threshold config + transfer to employee; callback task
- Sentiment timeline; call outcome classification; link to contact/deal/ticket

## BRUTAL FINDINGS (running total): 6 real bugs (M5,M6,M2,M10,M11,M13) +
## 3 compliance/safety gaps (M12 high-risk, M14 opt-in, M15 recording-consent).
## PATTERN: 3 of the gaps were "consent/flag recorded but never ENFORCED."

## ================================================================
## M15 COMBINED RUN — FINAL: 768 tests, 0 failed, 0 errors ✓
## AUTOMATED BRUTAL PASS: M1-M15 COMPLETE — FULL 15-MODULE BUILD GREEN
## ================================================================
All 15 modules green together. group_on quiet (7th cycle — permanently fixed).

### COMPLETE LIST OF REAL FINDINGS (9 total, all fixed):
Real bugs (6):
  1. M5  bank parser parsed US amounts as €0 (dropped transactions)
  2. M6  reschedule didn't re-arm reminder
  3. M2  credit card mislabeled [PHONE-REDACTED] (redaction order)
  4. M10 bijtelling inflated net pay (company-car overpayment)
  5. M11 accrual reversal unbalanced (could never post)
  6. M13 helpdesk portal controller never loaded (404)
Compliance/safety gaps (3) — ALL "consent/flag recorded but never enforced":
  7. M12 high-risk medical/financial not auto-detected (bot gave advice)
  8. M14 WhatsApp send ignored opt-in (policy violation)
  9. M15 call recording: silent record + false consent (wiretapping exposure)
Sound on probing: M7, M8, M9. Schema drift (group_on family) permanently fixed.

### TOP TAKEAWAY: original green suites hid every finding. The 3 compliance gaps
### shared one root pattern — consent was RECORDED but never ENFORCED at the
### decision point. Only adversarial "does it actually block?" tests caught them.

## REMAINING WORK (build complete — uploads exhausted):
1. CONSOLIDATED UI PASS (M3-M15, 13 modules) — main remaining risk.
2. Sign-off docs (M6-M15; M1-M5 done).

## ================================================================
## M16 FULL-SUITE CI GATE — CLEARED: 806 tests, 0 failed, 0 errors ✓
## All 18 modules upgraded + tested together in one run. First time at full scale.
## ================================================================
M16 security additions (company-isolation rules + cross-company isolation test)
all green. Full-suite-only test-isolation bugs found & fixed:
- subscription_modules: registry.clear_cache() in create() let (company,package)
  rows survive per-test rollback -> collisions. Fixed: clean-slate setUp in all
  3 test classes (matched existing pattern); deliberate-dup tests in savepoints.
- ai_chatbot: 3 deliberate-dup constraint tests wrapped in savepoints.
group_on quiet across the full 18-module upgrade. Secret storage verified encrypted.
