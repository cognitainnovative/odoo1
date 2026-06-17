# UI Testing Findings — Fixes (M1–M16 consolidated UI pass)

## 1. Live Chat crash "Missing 'card' template" — FIXED (custom_ai_chatbot)
chat_config_views.xml kanban used Odoo-18 template name <t t-name="kanban-card">.
Odoo 19 requires <t t-name="card">. (All other modules already used "card"; this
was the only stale one.) Fixed -> Live Chat kanban now loads.

## 2. CRM custom-field section error — FIXED (custom_crm_core)
Two problems: (a) the lead "Custom Fields" tab list omitted field_id (required), so
adding a row could not select which field -> save failed; (b) no menu existed to
DEFINE custom fields. Fixed: field_id now selectable in the value list; added
CRM > Configuration > Custom Fields action + list view + menu to manage definitions.

## 3. Invalid date range (end before start) not rejected — FIXED (general)
Many models had start/end date pairs with NO validation. Added @api.constrains
date-order guards to the high-impact ones:
  - rental.order: expected_return_date >= pickup_date
  - hr.sick.leave: expected_end_date >= start_date
  - platform.planning.job: end_datetime >= start_datetime
  - crm.campaign: end_date >= start_date
  - account.budget (platform): date_to >= date_from
  - account.accrual.provision: period_end >= period_start
(Each raises a clear ValidationError; verified each landed in the correct class.)

## 4. Quote signing accepted empty signature — ALREADY GUARDED (custom_quote_signing)
Current code rejects empty/near-empty signatures (portal.py: requires
signature_data length >= 60, else "Please draw or type your signature..."). If the
running instance still accepted empty, it was stale code — redeploy current version.
No code change needed; verify on the deployed build.

## 5. Website-added leaves not visible in records — FIXED (custom_hrm)
The website self-report form creates hr.sick.leave records, but /my/leaves only
read hr.leave (a different model) -> sick leaves were invisible there. Fixed: the
leaves controller now also fetches the employee's hr.sick.leave records, and the
"My Leaves" portal page renders a "My Sick Leave" section.

## 6. Payroll run executes without employee data — FIXED (custom_payroll_nl)
action_calculate searched for employees with payroll data but never checked the
result was empty; with none, it created a run with zero payslips and reported
success. Fixed: raises UserError "No employees with payroll data found..." when no
qualifying employees exist.

## 7. Live chat shows only the static backend message / wants a link — NEEDS DECISION
The bot DOES call RAG (call_with_rag). If only the configured greeting / a canned
"mock AI response" shows, the AI provider is on MOCK (no API key) — expected
without a real provider configured. The request to "add a link" is an ENHANCEMENT
(make responses/citations render as clickable links in the widget), not a defect.
Pending your decision on exact desired behavior before implementing.
