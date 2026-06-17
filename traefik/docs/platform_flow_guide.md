# Platform Flow Guide
## Complete Module Documentation & Business Flows

**Product:** Cognita Innovative — Modular ERP/CRM Platform on Odoo 19 Community  
**Version:** 1.0 — June 2026  
**Modules:** 17 custom modules covering CRM, Finance, HR, Payroll, Inventory, Rental, AI, Helpdesk, WhatsApp, Voice

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [Module Dependency Map](#2-module-dependency-map)
3. [Module 1 — custom_theme](#3-module-1--custom_theme)
4. [Module 2 — custom_subscription_modules](#4-module-2--custom_subscription_modules)
5. [Module 3 — custom_ai_core](#5-module-3--custom_ai_core)
6. [Module 4 — custom_crm_core](#6-module-4--custom_crm_core)
7. [Module 5 — custom_quote_signing](#7-module-5--custom_quote_signing)
8. [Module 6 — custom_accounting_basic](#8-module-6--custom_accounting_basic)
9. [Module 7 — custom_accounting_advanced](#9-module-7--custom_accounting_advanced)
10. [Module 8 — custom_hrm](#10-module-8--custom_hrm)
11. [Module 9 — custom_payroll_nl](#11-module-9--custom_payroll_nl)
12. [Module 10 — custom_inventory](#12-module-10--custom_inventory)
13. [Module 11 — custom_rental](#13-module-11--custom_rental)
14. [Module 12 — custom_planning](#14-module-12--custom_planning)
15. [Module 13 — custom_ai_chatbot](#15-module-13--custom_ai_chatbot)
16. [Module 14 — custom_helpdesk](#16-module-14--custom_helpdesk)
17. [Module 15 — custom_email_ai](#17-module-15--custom_email_ai)
18. [Module 16 — custom_whatsapp_social](#18-module-16--custom_whatsapp_social)
19. [Module 17 — custom_ai_voice](#19-module-17--custom_ai_voice)
20. [End-to-End Business Flows](#20-end-to-end-business-flows)
21. [Role & Access Matrix](#21-role--access-matrix)
22. [API Reference](#22-api-reference)

---

## 1. Platform Overview

This platform is a fully modular, commercially licensable ERP/CRM system built on Odoo 19 Community. Each module can be independently sold and activated per client company. The platform covers the complete business lifecycle — from the first customer contact through sales, invoicing, inventory, HR, payroll, and AI-powered communication.

### Core Design Principles

| Principle | Implementation |
|---|---|
| Modular licensing | Per-company subscriptions gate menu/feature access |
| AI-first | Every module has AI assistance (mock fallback when no key) |
| Audit-complete | All financial, payroll, signing and AI actions are immutable logs |
| GDPR-compliant | Consent tracking, anonymization, data minimization |
| Zero external dependency | Boots and runs core CRM with no API keys at all |
| Dutch-market ready | NL payroll (loonheffing, LHK, vakantiegeld), iDEAL, BV accounts |

### Technology Stack

| Layer | Technology |
|---|---|
| ERP Core | Odoo 19 Community |
| Language | Python 3.12 |
| Database | PostgreSQL 16 |
| AI Providers | Anthropic Claude / OpenAI / Ollama / Mock |
| VoIP | Twilio (TwiML webhooks) |
| STT | Deepgram (live) / OpenAI Whisper (batch) |
| TTS | ElevenLabs / OpenAI TTS |
| WhatsApp | Meta Cloud API / Twilio |
| Bank Import | CAMT.053 / MT940 / CSV |
| Signing | Electronic (simple/advanced) — not eIDAS qualified |
| Encryption | Fernet (provider API keys at rest) |

---

## 2. Module Dependency Map

```
custom_theme                    ← standalone, no dependencies
custom_subscription_modules     ← standalone, gates all other modules

custom_ai_core                  ← standalone AI engine
    └── used by:
        ├── custom_crm_core
        ├── custom_ai_chatbot
        ├── custom_helpdesk
        ├── custom_email_ai
        ├── custom_whatsapp_social
        └── custom_ai_voice

custom_crm_core                 ← requires: custom_ai_core
    └── custom_quote_signing    ← requires: custom_crm_core
            └── custom_rental   ← requires: custom_quote_signing

custom_accounting_basic         ← standalone
    └── custom_accounting_advanced ← requires: custom_accounting_basic

custom_hrm                      ← standalone
    └── custom_payroll_nl       ← requires: custom_hrm

custom_inventory                ← standalone
custom_planning                 ← requires: custom_crm_core

custom_helpdesk                 ← requires: custom_ai_core
    ├── custom_email_ai         ← requires: custom_helpdesk
    ├── custom_whatsapp_social  ← requires: custom_helpdesk
    └── custom_ai_voice         ← requires: custom_helpdesk
```

**Installation order:** theme → subscriptions → ai_core → crm → quote_signing → accounting_basic → accounting_advanced → hrm → payroll_nl → inventory → rental → planning → ai_chatbot → helpdesk → email_ai → whatsapp_social → ai_voice

---

## 3. Module 1 — `custom_theme`

### Purpose
Applies your company's complete visual identity across the entire platform — backend admin panel, customer portal, PDF documents, and email templates.

### What It Provides

| Feature | Detail |
|---|---|
| Company branding | Logo, favicon, primary/secondary/accent colors |
| Backend theme | Admin panel styled with brand colors and typography |
| Portal theme | Customer-facing pages styled to match brand |
| Brand CSS endpoint | `GET /web/platform/brand.css` — dynamically generated |
| PDF/email headers | Invoice and quote PDFs use company letterhead |

### Configuration

Navigate to: **Settings → Companies → [Your Company] → Branding Tab**

```
Fields to configure:
  Logo:            Upload PNG/SVG (recommended: 400×120px)
  Favicon:         Upload ICO/PNG (16×16 or 32×32)
  Primary Color:   #1E3A8A  (e.g. navy blue)
  Secondary Color: #F59E0B  (e.g. amber)
  Accent Color:    #10B981  (e.g. green)
  Font:            Inter / Roboto / Open Sans (or custom)
```

### Example — Cognita Innovative Setup

```
Before installation:  Default Odoo purple/blue theme
After configuration:
  ✅ All page headers: Navy blue (#1E3A8A)
  ✅ Top-left logo: Cognita logo (400×120px)
  ✅ Buttons and highlights: Amber (#F59E0B)
  ✅ Font everywhere: Inter (clean, professional)
  ✅ Customer portal: Identical branding
  ✅ PDF invoices and quotes: Cognita letterhead
  ✅ Email templates: Cognita colors and logo
```

### Impact on Other Modules
Every other module inherits this branding automatically. No additional configuration needed per module.

---

## 4. Module 2 — `custom_subscription_modules`

### Purpose
Controls which features each client company can access. Sells modules as packages with trial periods, activation dates, and expiry. When a subscription is inactive, all related menus and portal routes are automatically hidden — but data is preserved.

### Available Packages

| Package Code | Package Name | Modules Included |
|---|---|---|
| `crm_base` | CRM Base | CRM Core + Quote Signing |
| `finance_basic` | Finance Basic | Accounting Basic |
| `finance_advanced` | Finance Advanced | Accounting Advanced |
| `hrm` | HRM | HR Management |
| `payroll_nl` | Payroll NL | Dutch Payroll Engine |
| `inventory` | Inventory | Stock Management |
| `rental` | Rental | Full Rental Workflow |
| `ai_chat` | AI Chat | Chatbot + Employee App |
| `ai_voice` | AI Voice | VoIP + AI Voice Agent |
| `helpdesk` | Helpdesk | Tickets + SLA |
| `social` | Social Media | WhatsApp + Social Inbox |
| `planning` | Planning | Jobs + Calendar |
| `full_suite` | Full Suite | All modules |

### Subscription Lifecycle

```
Trial (default: 14 days)
    │
    ├── Activate manually → Active (with end date)
    │       │
    │       ├── End date passes → Expired
    │       │
    │       └── Manual cancel → Cancelled
    │
    └── Trial end passes → Expired
    
From any state → Reactivate → Active
```

### What Happens When Expired

```
Subscription expires:
  ✅ All data preserved (no deletion)
  ✅ Database records intact
  ❌ All related menus hidden
  ❌ Related portal routes blocked
  ❌ API endpoints return 403 Forbidden
  ℹ️  Admin sees "Subscription expired" banner
```

### Example — Three Client Companies

**Client A: ABC Transport BV**
```
Active Subscriptions:
  - CRM Base      (active, expires 2026-12-31)
  - Inventory     (active, expires 2026-12-31)

Visible menus:
  ✅ CRM → Leads, Deals, Contacts
  ✅ Inventory → Products, Stock, Purchase
  ❌ Payroll (hidden — not subscribed)
  ❌ Helpdesk (hidden — not subscribed)
  ❌ AI Voice (hidden — not subscribed)
```

**Client B: Cognita Rentals BV**
```
Active Subscriptions:
  - Full Suite    (trial, 7 days remaining)

Visible: Everything
Warning shown: "Trial expires in 7 days"
```

**Client C: HR Solutions BV**
```
Subscriptions:
  - HRM           (expired 2026-05-01)
  - Payroll NL    (expired 2026-05-01)

Result: All HR/Payroll menus hidden
All employee and payslip records preserved
Reactivate → immediate access restored
```

### Programmatic Access Check

```python
# Check from any Odoo code:
active = self.env['platform.subscription'].is_module_active('rental')
# Returns True if active/trial, False if expired/cancelled
# Returns True if NO subscriptions configured (fresh install default)
```

---

## 5. Module 3 — `custom_ai_core`

### Purpose
The AI brain of the entire platform. Provides a unified AI interface that all other modules use. Manages multiple AI providers, handles the RAG (knowledge base) pipeline, stores prompt templates with versioning, and maintains an immutable audit log of every AI interaction.

### AI Providers

| Provider | Best For | Required Key |
|---|---|---|
| **Mock** (default) | Testing, demo, no internet | None |
| **Anthropic Claude** | High-quality drafts, complex reasoning | `ANTHROPIC_API_KEY` |
| **OpenAI GPT** | Classification, fast responses | `OPENAI_API_KEY` |
| **Ollama** | Fully local/private, no data egress | `OLLAMA_BASE_URL` |
| **Azure OpenAI** | Enterprise data residency requirements | `AZURE_OPENAI_*` |

### Provider Fallback Chain

```
If preferred provider fails or no key:
  Anthropic → OpenAI → Ollama → Mock

System always answers — never crashes due to missing AI key.
Mock provider returns realistic placeholder responses for testing.
```

### RAG Pipeline (Knowledge Base)

```
INGEST PHASE:
  1. Upload document (PDF / DOCX / TXT / HTML / CSV)
  2. System chunks document into ~500 token pieces
  3. Each chunk embedded as a vector (pgvector or ILIKE fallback)
  4. Stored with: source, page number, company ID

SEARCH PHASE (on user question):
  1. User question → convert to embedding
  2. Vector similarity search → top 5 matching chunks
  3. Chunks passed to AI as context
  4. AI answers using chunks + cites the source

EXAMPLE:
  Documents uploaded:
    - Rental_Terms_2026.pdf
    - Camera_Equipment_Catalog.pdf
    - FAQ_Returns_Policy.pdf

  Customer asks: "What is the late return fee?"
  
  RAG finds: Rental_Terms_2026.pdf, page 3, chunk 7:
    "Late returns are charged at €75 per day..."
  
  AI answers: "The late return fee is €75 per day as
               per our rental terms (Section 3.2)."
  Citation: [Rental_Terms_2026.pdf, p.3]
```

### Prompt Template Store

```
Template: "helpdesk_reply_draft"
Version: 3
Variables: {company_name}, {customer_name}, {ticket_subject}, {ticket_body}

System prompt:
  "You are a professional support agent for {company_name}.
   Write an empathetic, helpful reply to the customer."

User prompt:
  "Customer: {customer_name}
   Subject: {ticket_subject}
   Message: {ticket_body}
   Draft a reply."

→ Version 3 saved, version 2 preserved for audit
→ AI outputs linked to template version used
→ Evaluation test cases per template
```

### AI Audit Log (Immutable)

```
Every AI call creates a log record:
  Timestamp:    2026-06-05 14:32:11 UTC
  User:         admin (Jan de Vries)
  Company:      Cognita Rentals BV
  Module:       custom_helpdesk
  Model:        claude-sonnet-4-5
  Template:     helpdesk_reply_draft v3
  Tokens In:    245
  Tokens Out:   312
  Cost Est:     €0.004
  Response:     [stored]

IMMUTABLE:
  → write() raises UserError: "Audit logs cannot be modified"
  → unlink() raises UserError: "Audit logs cannot be deleted"
  → Only system can create; no one can edit or delete
```

### Privacy & Data Redaction

```
Company setting: "Allow External AI" = OFF (default)
  → All AI calls use local Mock or Ollama
  → Zero data sent to Anthropic/OpenAI
  → Required for payroll and financial data (always local)

Company setting: "Allow External AI" = ON
  → Redaction applied BEFORE sending:
    BSN/SSN:     "My BSN is 123456789" → "My BSN is [REDACTED]"
    IBAN:        "IBAN NL91ABNA..." → "IBAN [REDACTED]"
    Email:       "jan@example.nl" → "[REDACTED_EMAIL]"
    Phone:       "+31612345678" → "[REDACTED_PHONE]"
  → Redacted prompt sent to external provider
  → Original (un-redacted) stored locally in audit log
```

---

## 6. Module 4 — `custom_crm_core`

### Purpose
A complete CRM system extending Odoo's built-in CRM. Covers the full sales lifecycle from lead capture through deal management, with AI lead scoring, duplicate detection, GDPR consent tracking, campaign management, and dashboards.

### Lead Object — Key Fields

```
Identity:
  Name, Email, Phone, Company name
  Linked partner (res.partner)

Sales:
  Pipeline stage, Probability (%)
  Expected revenue, Close date
  Assigned salesperson, Sales team

Platform Extensions:
  Lead Score (0-100, auto-calculated)
  AI Summary (generated on demand)
  Platform Campaign (crm.campaign record)
  Source Detail (e.g. "Google Ads – Brand")
  Next Follow-up Date
  Last Contacted Date, Contact Attempts

GDPR:
  Consent Given (boolean)
  Consent Date, Consent IP
  Privacy Policy Version accepted
  Anonymized (boolean, irreversible)
```

### Lead Scoring Algorithm

The score is automatically calculated and stored when key fields change:

```
Scoring rules:
  +20  Email address present
  +15  Phone number present
  +10  Linked to existing partner record
  +5   Partner has a website
  +2   Per €1,000 expected revenue (capped at +20)
  +15  Probability above 50%
  Maximum possible: 100

Example — "Pieter de Vries - Software Project":
  Email present:       +20
  Phone present:       +15
  Partner linked:      +10
  Expected €15,000:    +15  (capped)
  Probability 60%:     +15
  SCORE: 75/100  →  Hot lead — follow up today
```

### Duplicate Detection

```
When a new lead is created or email is entered:
  System checks: same email domain, same company name, same phone

Example:
  New lead: "Jan Jansen, jan@acme.nl"
  Existing: "J. Jansen, j.jansen@acme.nl"

  → Warning: "1 possible duplicate found"
  → Click to compare side-by-side
  → Merge contacts (keeps combined history)
  → Duplicate count shown on lead form
```

### Campaign Management

```
Campaign: "Summer Rental Promotion 2026"
  Type: Email Campaign
  Start: 2026-06-01
  End:   2026-08-31
  Budget: €5,000
  Target audience: All Amsterdam contacts

Leads tagged with this campaign:
  → Track source of every lead
  → See campaign ROI in dashboard:
    "Summer Rental 2026 → 23 leads → 8 won → €45,000 revenue"
```

### GDPR Flow

```
Lead from website form:
  → gdpr_consent: True (checkbox on form)
  → gdpr_consent_date: 2026-06-05 14:30:00
  → gdpr_consent_ip: 82.161.xx.xx
  → gdpr_consent_version: "privacy-v2.1"

Customer requests data removal:
  Action: CRM → Lead → Action menu → "Anonymize Lead"
  
  System changes:
    name:  "Anonymous"
    email: "anon_a3f4b2@deleted.invalid"
    phone: False
    partner_id: False
    gdpr_anonymized: True  (irreversible)
  
  Preserved: deal history, revenue figures, stage progression
  Deleted: all personally identifiable information
```

### CRM Dashboard Metrics

```
Real-time dashboard (CRM → Dashboard):
  ┌────────────────────────────────────────────┐
  │ New Leads This Week:      12               │
  │ Open Deals:               34  (€180,000)   │
  │ Closing This Month:        8  (€ 45,000)   │
  │ Won This Month:            5  (€ 32,000)   │
  │ Lost This Month:           3               │
  │ Conversion Rate:          62.5%            │
  │                                            │
  │ By Salesperson:                            │
  │   Jan de Vries:   8 deals  €65,000        │
  │   Maria Santos:   6 deals  €48,000        │
  │                                            │
  │ Lead Sources:                              │
  │   Website:   45%                           │
  │   Referral:  30%                           │
  │   Cold Call: 15%                           │
  │   Other:     10%                           │
  └────────────────────────────────────────────┘
```

---

## 7. Module 5 — `custom_quote_signing`

### Purpose
Provides a secure, browser-based customer signing portal for sales quotes. The customer receives a link via email, reviews the quote with price clearly shown, accepts the terms, and signs digitally. Full audit evidence is captured and stored immutably for legal admissibility.

### Quote Lifecycle

```
Draft
  ↓  Salesperson clicks "Send for Signing"
Sent  (email dispatched with unique secure link)
  ↓  Customer opens the link
Viewed  (timestamp recorded)
  ↓  Customer reads terms and ticks checkbox
Accepted Pending
  ↓  Customer types name and clicks "Confirm & Sign"
Signed  (full audit evidence stored, signed PDF generated)
  ↓  Automatic confirmation
Confirmed  (deal marked Won)
  ↓  Invoice generated
Invoiced
  ↓  or manual cancel at any stage
Cancelled / Expired (after configurable days)
```

### Customer Portal Page

```
URL: https://yoursite.com/quote/abc123xyz456

The page displays:
  ┌──────────────────────────────────────────────┐
  │  QUOTE #SO/2026/0042                         │
  │  Cognita Innovative                          │
  │  Date: 2026-06-05   Valid until: 2026-07-05  │
  │                                              │
  │  For: Pieter de Vries, Acme BV               │
  │                                              │
  │  ITEMS:                                      │
  │  Software Implementation      €10,000.00     │
  │  Annual Support Contract       €5,000.00     │
  │  ─────────────────────────────────────────   │
  │  Subtotal excl. VAT:          €15,000.00     │
  │  VAT 21%:                      €3,150.00     │
  │  TOTAL DUE:                   €18,150.00     │
  │                                              │
  │  [View Full Terms & Conditions ↗]            │
  │                                              │
  │  ☐ I have read and accept the Terms &        │
  │    Conditions and acknowledge my payment     │
  │    obligation of €18,150.00 incl. VAT.       │
  │                                              │
  │  Your full name:  [___________________]      │
  │                                              │
  │  [  CONFIRM & SIGN QUOTE  ]                  │
  └──────────────────────────────────────────────┘
```

### Audit Evidence Captured

Every signing event stores the following immutable record:

```
quote.signing record (cannot be modified or deleted):
  signer_name:        "Pieter de Vries"
  signer_email:       "p.devries@acme.nl"
  signed_at:          2026-06-05 14:32:11 UTC
  ip_address:         "82.161.xx.xx"
  user_agent:         "Mozilla/5.0 Chrome/125.0..."
  terms_version:      "terms-v3.1"
  terms_accepted:     True
  payment_accepted:   True
  document_version:   "v2"
  document_hash:      "a3f4e2b1c9d8..." (SHA-256, tamper-proof)
  event_log:
    14:30:01 — Secure link opened
    14:31:45 — Terms & Conditions popup viewed (full scroll)
    14:32:08 — Acceptance checkbox ticked
    14:32:11 — Quote signed and submitted

All fields: IMMUTABLE. write() and unlink() raise UserError.
```

### Automatic Post-Signing Actions

```
Quote signed →
  1. Sale order state: Confirmed
  2. CRM deal state: Won
  3. Planning job auto-created: "Implementation — Pieter de Vries"
     Assigned to: delivery team
     Due date: 5 working days from signing
  4. Signed PDF generated (with signature embedded)
  5. Email to customer: "Your signed quote — PDF attached"
  6. Internal notification to salesperson Jan
  7. Invoice draft created (optional, configurable)
```

### Legal Note

```
This module implements a Simple/Advanced Electronic Signature.
This is legally valid for most commercial contracts in the EU.

It is NOT an eIDAS Qualified Electronic Signature.
If a client requires qualified signatures (for high-value contracts,
real estate, regulated industries), a QTSP (Qualified Trust Service
Provider) integration is required — this is an external approval
blocker and must be arranged separately.
```

---

## 8. Module 6 — `custom_accounting_basic`

### Purpose
Handles all day-to-day accounting operations: outgoing invoices, incoming supplier bills with OCR extraction, bank statement import in three formats, and AI-powered payment matching/reconciliation.

### Bank Import Formats

| Format | Description | Source |
|---|---|---|
| **CSV** | Comma-separated, most online banking exports | Any bank |
| **MT940** | Traditional SWIFT bank statement format | ING, ABN AMRO, Rabobank |
| **CAMT.053** | Modern ISO 20022 XML format | All EU banks (PSD2) |

### Bank Import & AI Reconciliation Flow

```
STEP 1: Import bank statement
  Accounting → Import Bank Statement → Upload file
  → Transactions parsed and displayed

STEP 2: AI matching runs automatically
  For each transaction, AI checks:
    - Invoice number in description
    - IBAN match with known parties
    - Exact amount match
    - Party name similarity
    - Date proximity to invoice due date

STEP 3: Results shown with confidence scores

Example bank statement after import:
  ┌──────────────────────────────────────────────────────────┐
  │ +€15,000  "BETALING INV 2026-042 PIETER DE VRIES"        │
  │   → AI Match: INV/2026/0042 — Pieter de Vries            │
  │   → Confidence: 98% ✅ — Recommended: Reconcile          │
  │                                                          │
  │ +€3,500   "HUUR BETALING JUNI SARAH VAN DEN BERG"        │
  │   → AI Match: Rental INV/2026/0089 — Sarah               │
  │   → Confidence: 87% — Review recommended                 │
  │                                                          │
  │ -€2,340   "FACTUUR TECHPARTS BV 445"                     │
  │   → AI Match: Supplier bill TP-2026-445                  │
  │   → Confidence: 76% — Review recommended                 │
  │                                                          │
  │ +€450     "Betaling"                                     │
  │   → No match found                                       │
  │   → Placed in Unknown Payments Queue                     │
  └──────────────────────────────────────────────────────────┘

STEP 4: One-click reconcile all 90%+ matches
STEP 5: Manually review lower confidence matches
STEP 6: Unknown payments assigned to holding account
```

### Incoming Invoice OCR

```
FLOW: Upload supplier PDF → AI extracts → Review → Post

Upload: techparts_invoice_may.pdf

AI Extraction Result:
  ┌──────────────────────────────────────┐
  │ Supplier:    TechParts BV            │
  │ KvK:         12345678                │
  │ IBAN:        NL91 ABNA 0417 1643 00  │
  │ Invoice No:  TP-2026-445             │
  │ Invoice Date: 2026-05-28             │
  │ Due Date:    2026-06-28              │
  │                                      │
  │ Lines:                               │
  │  Laptop Stand × 10  →  €200.00      │
  │  USB Hub × 5        →  €125.00      │
  │  ──────────────────────────────      │
  │  Subtotal:              €325.00      │
  │  VAT 21%:                €68.25      │
  │  Total:                 €393.25      │
  └──────────────────────────────────────┘

Duplicate check: No existing bill found ✅

Booking Proposal:
  Debit:  Equipment Expense     €325.00
  Debit:  VAT Input              €68.25
  Credit: Accounts Payable      €393.25

→ Finance manager reviews → Approves → Posted
```

### Payment Scenarios

```
Exact payment:
  Invoice: €18,150 → Payment: €18,150 → Fully Paid ✅

Partial payment:
  Invoice: €18,150 → Payment: €10,000 → Partially Paid
  Remaining: €8,150 outstanding
  Follow-up reminder scheduled

Overpayment:
  Invoice: €18,150 → Payment: €18,500 → Paid + €350 credit
  Credit moves to Unknown Payments Queue for review

Split payment (2 transactions for 1 invoice):
  Transaction 1: €10,000 → matched to invoice (partial)
  Transaction 2: €8,150 → matched to same invoice (completes it)
  → Invoice: Fully Paid ✅
```

---

## 9. Module 7 — `custom_accounting_advanced`

### Purpose
Advanced financial management for finance managers and accountants. Covers fixed asset tracking with depreciation schedules, fiscal year management with period locks, BV annual accounts preparation, budget vs actual reporting, and audit file export.

### Fixed Assets

```
SETUP EXAMPLE — Company Van:
  Asset name:       "Mercedes Sprinter Van"
  Category:         Vehicle
  Acquisition date: 2024-01-01
  Acquisition value: €45,000
  Residual value:   €5,000
  Useful life:      5 years
  Method:           Straight-line depreciation
  Status:           Active

Annual depreciation = (€45,000 - €5,000) / 5 = €8,000/year

DEPRECIATION SCHEDULE (auto-generated):
  ┌──────┬────────────┬──────────────┬────────────┐
  │ Year │ Depr. (€)  │ Accum. (€)   │ NBV (€)    │
  ├──────┼────────────┼──────────────┼────────────┤
  │ 2024 │  8,000     │  8,000       │ 37,000     │
  │ 2025 │  8,000     │ 16,000       │ 29,000     │
  │ 2026 │  8,000     │ 24,000       │ 21,000     │
  │ 2027 │  8,000     │ 32,000       │ 13,000     │
  │ 2028 │  8,000     │ 40,000       │  5,000     │
  └──────┴────────────┴──────────────┴────────────┘

DISPOSAL EXAMPLE (sold in 2027 for €15,000):
  Net book value at disposal: €13,000
  Sale price:                 €15,000
  Gain on disposal:           +€2,000 → posted to P&L
  Asset status:               Disposed
  Journal entry:              auto-created
```

### Fiscal Year & Period Locks

```
Fiscal Year 2025:
  Start:      2025-01-01
  End:        2025-12-31
  Status:     Closed
  Lock date:  2026-01-31

Effect of lock:
  Attempt to post journal entry dated Dec 2025 on Feb 1 2026:
  → Error: "Period is locked. No entries allowed before 2026-02-01."

Admin override (when auditor requires correction):
  Admin enters reason: "Correcting Dec 2025 accrual per audit finding ref #A-234"
  → Override allowed
  → Audit log: "Period lock override by admin on 2026-02-15, reason: [...]"
  → Entry posted with override flag visible on the record
```

### Budget vs Actual

```
Budget defined for 2026:
  Department: Marketing
  Q1: €10,000  Q2: €12,000  Q3: €15,000  Q4: €13,000
  Annual: €50,000

Report as of June 2026:
  ┌─────────────────────────────────────────────────┐
  │ Marketing Budget vs Actual — June 2026          │
  │                                                 │
  │ Q1 Budget: €10,000 | Actual: €9,500  | 95% ✅  │
  │ Q2 Budget: €12,000 | Actual: €7,200  | 60% ✅  │
  │                                                 │
  │ H1 Total Budget:  €22,000                       │
  │ H1 Actual Spend:  €16,700                       │
  │ Remaining H1:      €5,300                       │
  │                                                 │
  │ Forecast warning: June spend rate suggests      │
  │ Q3 may exceed budget by ~€2,000                 │
  └─────────────────────────────────────────────────┘
```

### BV Annual Accounts

```
Company type: BV (Besloten Vennootschap)

Annual accounts package (prepared in system, filed externally):
  ✅ Balance sheet as of 31-12-2025
  ✅ Profit & Loss statement
  ✅ Notes to accounts (template, editable)
  ✅ Equity overview:
       Opening equity:       €150,000
       Net profit 2025:      +€45,000
       Dividends paid:       -€20,000
       Closing equity:       €175,000
  ✅ Accountant review workflow:
       → Share draft with external accountant (special access role)
       → Accountant adds review notes
       → Director approves final version
  ✅ Export to PDF and Word

Filing: Must be done manually via KVK/external accountant.
This module prepares the package; it does not auto-file.
```

---

## 10. Module 8 — `custom_hrm`

### Purpose
Complete employee lifecycle management with a self-service portal. Employees manage their own data, request leave, report sick, and download payslips directly from the portal without HR involvement for routine tasks.

### Employee Record

```
Personal (HR-only access):
  Full name, date of birth, BSN (encrypted, last-4 visible)
  Nationality, emergency contact name and phone

Work:
  Employee ID: EMP-0042
  Department: Marketing
  Job title: Marketing Manager
  Manager: Jan de Vries
  Start date: 2022-05-01
  Contract type: Full-time, 40h/week

Documents:
  Employment contract: signed 2022-05-01 (PDF stored)
  ID copy: uploaded and encrypted
  Certifications: Google Analytics (expires 2027-01-01)
    → Automatic reminder 90 days before expiry

Equipment:
  MacBook Pro M3 (serial: C02xxx)
  iPhone 15 (IMEI: 35xxx)
  → Equipment return checklist on offboarding
```

### Employee Self-Service Portal

```
Available at: https://yoursite.com/my/

Pages:
  /my/profile       → Edit address, emergency contact, bank account
  /my/leaves        → View balance, request new leave
  /my/sick-leave/report → Report sick today
  /my/payslips      → List and download own payslips (own only)
  /my/documents     → HR documents to review and optionally sign
  /my/planning      → View own work schedule

Security:
  → Employee sees ONLY their own payslips (record rule enforced)
  → Employee cannot access any other employee's data
  → HR manager sees all employees
  → Payroll manager sees payroll data only
```

### Leave Request Flow

```
EMPLOYEE (portal):
  Type: Annual Leave (vacation)
  From: 2026-07-21
  To:   2026-07-25 (5 working days)
  Note: "Family holiday to Portugal"
  → Submitted

SYSTEM checks:
  → Current balance: 15 days available
  → Requested: 5 days
  → Conflicts with other team members: none
  → Overlaps with public holidays: none

MANAGER (Jan de Vries, email notification):
  Opens Odoo → HR → Leave Requests
  → Reviews Maria's request
  → Approves ✅

RESULT:
  → Maria's balance: 15 → 10 days
  → Calendar: Maria absent July 21-25 (visible to team)
  → Planning: No jobs assigned to Maria those 5 days
  → Maria receives approval email
```

### Sick Leave Flow (Privacy-Safe)

```
EMPLOYEE (portal, Monday morning):
  Reports: "I am sick today, 2026-06-10"
  Expected return: Unknown

SYSTEM records:
  ✅ Absence date: 2026-06-10
  ✅ Manager notification sent to Jan de Vries
  ❌ NO medical condition stored
  ❌ NO diagnosis stored
  ❌ NO doctor's certificate content stored
  (GDPR: medical data is sensitive — only absence timing kept)

THURSDAY:
  Employee reports recovery: "Returning Monday 2026-06-15"

RESULT:
  Absence recorded: 2026-06-10 to 2026-06-12 (3 working days)
  HR sees: "3-day absence" — nothing medical visible
  Payroll: sick days deducted from balance per contract rules
```

### Onboarding Checklist

```
New hire: Thomas Bakker, start date: 2026-07-01

Auto-created checklist:

  PRE-START (week -1):
    ☐ Laptop ordered and configured  (IT: Mark)
    ☐ Email account created          (IT: Mark)
    ☐ Access cards arranged          (Office: Lisa)

  WEEK 1:
    ☐ Employment contract signed     (HR: Maria)
    ☐ NDA signed                     (Legal: Director)
    ☐ Office and team introduction   (Manager: Jan)
    ☐ System logins provided         (IT: Mark)

  MONTH 1:
    ☐ 30-day check-in meeting        (Manager: Jan)
    ☐ Goals and KPIs agreed          (Manager: Jan)

  PROBATION END (6 months):
    ☐ Probation evaluation           (HR: Maria + Jan)
    ☐ Contract extension or decision

Reminders:
  D-7: "Thomas starts in 7 days — prepare laptop"
  D-0: "Thomas starts today — checklist live"
  D+30: "30-day check-in due with Thomas Bakker"
```

---

## 11. Module 9 — `custom_payroll_nl`

### Purpose
A complete Dutch payroll calculation engine with versioned tax parameter tables. Calculates loonheffing (wage tax), loonheffingskorting (tax credit), vakantiegeld (holiday allowance), pension contributions, AWF and ZVW employer contributions. Generates payslip PDFs and publishes them to the employee portal. Exports data for accountants and payroll providers.

### Employee Payroll Profile

```
Employee: Maria Santos
Gross monthly salary:   €3,500.00
Contract hours:         40/week
LHK (tax credit):       Yes (applies loonheffingskorting)
Pension employee %:     4%
Pension employer %:     6%
Travel allowance:       €150/month (tax-free within limits)
Company car:            No
Bonus:                  Calculated per run if applicable
```

### Payslip Calculation — June 2026

```
GROSS INCOME:
  Base salary:                €3,500.00
  Travel allowance:           €  150.00
  ─────────────────────────────────────
  Taxable gross:              €3,650.00

LOONHEFFING CALCULATION:
  Bracket: €0–€38,441 @ 35.82%
  Tax on €3,650 × 12 = €43,800/year: €14,978
  Monthly tax:                €1,248.17
  LHK credit (2025):          -€  255.83
  Net loonheffing:            €  992.34

  (Note: LHK phases out for higher incomes)

EMPLOYEE DEDUCTIONS:
  Loonheffing:                -€  992.34
  Pension contribution (4%): -€  140.00
  ─────────────────────────────────────
  NET SALARY:                 €2,517.66

EMPLOYER CONTRIBUTIONS (not deducted from employee):
  AWF/WW (0.47%):             €   17.16
  ZVW employer (6.51%):       €  237.62
  Pension employer (6%):      €  210.00
  ─────────────────────────────────────
  Total employer cost:        €2,982.44

VAKANTIEGELD ACCRUAL:
  Rate: 8% of gross
  This month: €3,500 × 8% =  €  280.00
  YTD accrued (6 months):    €1,680.00
  (Typically paid out in May each year)

JOURNAL ENTRY (auto-created):
  Dr. Wage Expense:          €3,650 + €464.78 (emp. contrib.)
  Cr. Salary Payable:        €2,517.66
  Cr. Loonheffing Payable:   €  992.34
  Cr. Pension Fund Payable:  €  350.00
```

### Versioned Rules Engine

```
Rule Version: 2025-NL (currently active)
  lhk_max:               €3,070
  lhk_phase_out_start:   €23,898
  lhk_phase_out_end:     €73,031
  awf_rate:              0.0047
  zvw_rate:              0.0651
  zvw_max_annual_wage:   €75,518
  vakantiegeld_pct:      8.0

January 2026: Create Rule Version 2026-NL
  → Update only changed rates
  → Old payslips keep their 2025-NL version permanently
  → No retroactive recalculation

Manual override with audit trail:
  Override: Jan de Vries, Gross €3,500 → €4,000
  Reason required: "Q2 performance bonus approved by director on 2026-06-01"
  → Override record IMMUTABLE
  → Calculation explanation stored as JSON for full transparency
```

### Monthly Payroll Run Process

```
STEP 1 — Create Payroll Run
  Reference: "June 2026 Monthly Payroll"
  Period: 2026-06-01 to 2026-06-30
  Rule version: 2025-NL
  Payroll journal: General Journal

STEP 2 — Calculate (click "Calculate All")
  System processes each active employee:
  ✅ Maria Santos        — calculated
  ✅ Jan de Vries        — calculated
  ✅ Thomas Bakker       — calculated (partial month, started June 15)
  ✅ 7 more employees    — calculated
  
  Run summary:
    Employees: 10
    Total gross: €38,500
    Total loonheffing: €9,800
    Total net: €26,700
    Total employer cost: €46,200

STEP 3 — Manager Review
  Finance manager opens each payslip
  Suspicious value? Click → see full calculation JSON
  Add override if needed (with reason)

STEP 4 — Confirm
  State: Draft → Confirmed
  Payslips locked for editing

STEP 5 — Approve
  State: Confirmed → Approved
  Director/HR manager approval recorded

STEP 6 — Publish to Portal
  State: Approved → Published
  All employees can now see and download their payslip
  Notification email sent to each employee

STEP 7 — Post Journal Entry
  Accounting entries created and posted
  Linked to account.move record

STEP 8 — Export
  CSV export: for accountant
  PDF export: for payroll provider / archiving

LEGAL NOTE: Belastingdienst loonaangifte must be filed via a
certified software route. This module prepares all data and
exports. Your accountant or payroll provider handles the
official electronic filing.
```

---

## 12. Module 10 — `custom_inventory`

### Purpose
Complete inventory management covering products, warehouses, stock movements, purchase orders, bundle products, reorder rules, stock valuations, and a dashboard for stock health.

### Product Setup

```
Product: Sony FX3 Professional Camera Kit
Type: Storable product (is_storable=True)
SKU: CAM-FX3-001
Barcode: 1234567890123
Category: Camera Equipment

Stock levels:
  On Hand:   3 units
  Reserved:  1 unit (Rental order RO-042)
  Available: 2 units
  Incoming:  2 units (Purchase order PO-089, arriving June 15)

Valuation:
  Cost (FIFO): €3,200 per unit
  Total value: €9,600 (3 units on hand)

Reorder rule:
  Min quantity: 2 units
  Max quantity: 5 units
  → When available < 2: auto-suggest purchase order for (max - current) units

Primary supplier: Sony Netherlands BV
  Unit price: €3,200
  Lead time: 14 days
  Minimum order: 1 unit
```

### Stock Movement Flow

```
Sale confirmed: SO/2026/0042 — 1× Sony FX3 Kit to Pieter

Stock move created:
  Type: Customer Delivery (OUT)
  Product: Sony FX3 Kit
  From: Main Warehouse / Stock
  To: Customer location (Pieter de Vries)
  Quantity: 1
  Status: Confirmed → Done

Stock update:
  On Hand:   3 → 2
  Available: 2 → 1

Reorder check runs:
  Available (1) < Reorder minimum (2) → ALERT
  → Draft purchase order auto-created:
    Supplier: Sony Netherlands BV
    Quantity: 4 (to reach max of 5)
    Total: €12,800
    Status: Draft — awaiting purchasing manager review
```

### Bundle Products

```
Bundle: "Full Film Production Kit"
Components:
  × 1  Sony FX3 Camera
  × 2  64GB SD Cards
  × 1  Professional Camera Bag
  × 1  Carbon Fibre Tripod
  × 1  Battery Pack (extra)

Order 2× "Full Film Production Kit":
  System auto-deducts ALL components:
  - Sony FX3 Camera:    -2 units
  - 64GB SD Cards:      -4 units
  - Camera Bags:        -2 units
  - Tripods:            -2 units
  - Battery Packs:      -2 units

Individual component stock updated accordingly.
If any component is out of stock → order blocked with warning.
```

### Inventory Dashboard

```
Low Stock Alerts:
  ⚠️  USB Hub Model A:       1 unit (min: 5) — ORDER NEEDED
  ⚠️  Laptop Stand Pro:      3 units (min: 10) — ORDER NEEDED
  ✅  Sony FX3 Kit:          4 units (min: 2) — OK

Fast Movers — Last 30 Days:
  1.  Camera Bag:          18 units sold
  2.  Sony FX3 Kit:         8 units sold
  3.  64GB SD Card:        24 units sold

Stock Valuation:
  Camera Equipment:   €95,000
  Accessories:        €45,000
  Other:              €18,400
  Total:             €158,400

Out of Stock:         2 products
Overstock warnings:   1 product (>180 days supply)
```

---

## 13. Module 11 — `custom_rental`

### Purpose
A complete rental business management system. Handles the full lifecycle from quote to deposit release, including availability calendars, ID verification, customer discount tiers, damage reports, late fees, and recurring billing.

### Rental Product Configuration

```
Product: Sony FX3 Professional Camera Kit

Pricing:
  Per day:      €150.00
  Per week:     €800.00  (save €250 vs daily)
  Per month:    €2,500.00 (save €2,000 vs daily)
  Weekend rate: €300.00  (Friday pickup to Monday return)
  Minimum period: 1 day

Add-on fees:
  Deposit:          €1,000 (refundable)
  Insurance / day:  €15.00
  Cleaning fee:     €25.00 (flat, per rental)
  Damage waiver/day: €20.00 (optional, waives damage claims)
  Late return fee:  €75.00 per day

Total units in fleet: 3
Maximum concurrent rentals: 3 (fully utilized = no more bookings)
```

### Customer Discount Tiers

```
Tier         Annual Spend    Discount    Approval Required
Standard     < €10,000        0%         —
Silver       €10,000+         5%         —
Gold         €25,000+        10%         —
Platinum     €50,000+        15%         —
Negotiated   manual          custom      Manager approval + reason

Auto-tier: System checks annual spend each month and upgrades automatically.
Sarah van den Berg: annual spend €28,000 → auto-assigned Gold (10% discount).

Manual override > 20% discount:
  Requires: written reason + named approver
  Logged: immutable discount approval audit record
```

### Full Rental Lifecycle — Wedding Photographer Example

```
Customer: Sarah van den Berg (Gold tier: 10% discount)
Product: Sony FX3 Professional Camera Kit
Period: 20 June – 22 June 2026 (3 days)

STEP 1: QUOTE CREATED
  Base rental:   3 × €150 = €450.00
  Gold discount (10%):      -€45.00
  Insurance:     3 × €15 =  €45.00
  Cleaning fee:             €25.00
  ─────────────────────────────────
  Rental total:            €475.00
  Deposit:                €1,000.00
  ─────────────────────────────────
  Due at pickup:          €1,475.00
  (Deposit is fully refundable)

STEP 2: SIGNING
  Quote sent → Sarah opens portal
  Sarah signs digitally
  Audit evidence stored (M5)
  Availability: June 20-22 RESERVED

  Availability calendar update:
    Unit 1 of 3: BOOKED (June 20-22)
    Unit 2 of 3: Available
    Unit 3 of 3: Available
    → Other customers can still book units 2 and 3

STEP 3: ID VERIFICATION (legal requirement for deposits)
  ID type: Dutch Passport
  BSN last 4 digits: 5678 (only last 4 stored — minimal PII)
  ID expiry: 2028-10-15
  KvK: Not applicable (private individual)
  Risk flag: Low
  Data retention: 6 months from rental end (configurable)

STEP 4: PICKUP — June 20, 14:00
  Condition at pickup: "Perfect — all accessories present, no damage"
  Condition notes signed off by Sarah
  Deposit: €1,000 received
  Pickup record created

  Inventory:
    Unit 1: Status → Active rental (not available for other bookings)
    On-hand count: 3, Available for new bookings: 2

STEP 5: DURING RENTAL — Monitoring
  System monitors: Return expected June 22 by 18:00
  Automatic reminder sent June 22 at 10:00:
    "Your Sony FX3 Kit is due back today by 18:00.
     Please contact us if you need an extension."

STEP 6: RETURN — June 22, 17:30
  Return recorded: on time ✅
  Inspection notes: "Small scratch on lens cap, otherwise perfect"
  Damage description: "1cm scratch on lens cap from external use"
  Damage cost: €25.00

  Final calculation:
    Rental paid:        €475.00 ✅
    Damage charge:      €25.00
    ─────────────────────────────
    Deposit applied:    -€25.00 (damage deducted)
    Deposit refund:     €975.00

STEP 7: FINAL INVOICE
  Invoice: Damage charge €25.00
  Deposit: €1,000 - €25 = €975 refund to Sarah
  Invoice status: Paid ✅

STEP 8: STOCK RETURNED
  Unit 1: Status → Available ✅
  Available for new bookings: 3 units again
  Rental order status: Closed
```

---

## 14. Module 12 — `custom_planning`

### Purpose
Job, appointment, and resource scheduling system. All accepted quotes, completed signings, rental pickups/returns, and support callbacks automatically create planning tasks. Provides a calendar view, employee availability management, and completion reporting.

### Planning Job Types

```
Auto-created from other modules:
  Quote signed          → "Implementation/delivery job"
  Rental reserved       → "Rental pickup" + "Rental return"
  Helpdesk callback     → "Support callback"
  AI Voice callback     → "Callback — caller from +31xxx"

Manually created:
  Sales visit, Demo, Installation, Service, HR meeting, Internal task
```

### Job Fields

```
Title: "Software Implementation — Pieter de Vries"
Type: Implementation
Status: Scheduled → In Progress → Completed / Cancelled

Linked to:
  Sale order: SO/2026/0042 (auto-linked from signing)
  Customer: Pieter de Vries (Acme BV)
  Lead: CRM lead #L-089

Scheduling:
  Planned date: 2026-06-20
  Duration: 2 days
  Location: Amsterdam (with travel notes)

Team:
  Lead: Jan de Vries
  Support: Thomas Bakker

Notifications:
  → Customer confirmation email: "Your appointment is confirmed for June 20"
  → Reminder email to customer: June 19 (day before)
  → Reminder to team members: June 19 18:00
```

### Calendar View

```
Week of June 20, 2026:

Monday:
  09:00 Jan → Client visit (Acme BV)
  14:00 Thomas → Rental pickup (Sarah — FX3 Kit)

Tuesday:
  Full day: Jan + Thomas → Implementation (Pieter / Acme)

Wednesday:
  10:00 Maria → HR meeting (onboarding Thomas)
  17:30 Thomas → Rental return inspection (Sarah)

Colour coding:
  🔵 Implementation/Delivery
  🟡 Rental pickup/return
  🟢 Sales visit
  🔴 Overdue / SLA breach
```

### Completion Report

```
Job completed: "Software Implementation — Pieter de Vries"
  Completion date: 2026-06-21 (1 day early ✅)
  Completed by: Jan de Vries + Thomas Bakker
  Hours spent: 14 (planned: 16)
  Notes: "All modules installed and configured. Training delivered."
  Customer satisfaction: Signed completion form ✅

→ Final invoice status: Ready to generate
→ Planning calendar: Job marked complete
→ CRM: Deal fully delivered
```

---

## 15. Module 13 — `custom_ai_chatbot`

### Purpose
A consent-aware website chat widget powered by AI and the RAG knowledge base. Visitors ask questions, the AI answers using company documents, captures lead information, and escalates to a human agent when confidence is low, the visitor requests a human, or frustration/anger is detected.

### Chat Session Flow

```
VISITOR → Website chat bubble clicked

Step 1 — Consent
  Popup: "We use tracking to improve your experience. Accept?"
  Visitor: Accept / Decline
  If declined: Chat still works, no tracking stored

Step 2 — Greeting (configurable per company)
  "Hi! I'm the Cognita Rentals assistant. 
   How can I help you today?"

Step 3 — Visitor question
  "Do you have professional cameras available for this weekend?"

Step 4 — RAG search
  Query: "professional cameras available weekend"
  Documents searched: Camera_Catalog.pdf, Pricing_Guide.pdf
  Top chunks found:
    - Sony FX3 Kit: €150/day, €300/weekend
    - Canon EOS R5: €120/day, €240/weekend

Step 5 — AI answer with citation
  "Yes! We have two great options available this weekend:
   • Sony FX3 Professional Kit — €300 for the weekend
   • Canon EOS R5 — €240 for the weekend
   Both include accessories and a camera bag.
   Would you like to check specific availability or get a quote?"
  [Source: Camera Catalog 2026, Pricing Guide p.3]

Step 6 — Lead capture
  "That sounds great! Can I get a quote for the Sony FX3?"
  Bot: "Of course! What's your name and email address?"
  Visitor: "Sophie Lens, sophie@studio.nl"
  
  → CRM Lead auto-created:
      Name: Sophie Lens
      Email: sophie@studio.nl
      Source: Website Chat
      Interest: Sony FX3 Kit rental (weekend)
      Session transcript: attached
```

### Escalation Triggers

```
Escalation happens automatically when:

1. LOW CONFIDENCE (AI not sure of answer):
   AI confidence < 45% → "Connecting you with our team..."
   Reason logged: low_confidence

2. VISITOR REQUESTS HUMAN:
   "I want to talk to a person"
   "Can I speak to someone?"
   → Immediate escalation
   Reason logged: human_requested

3. TRIGGER WORDS:
   "lawsuit", "lawyer", "fraud", "police", "emergency"
   → Immediate escalation
   Reason logged: trigger_word

4. FRUSTRATION / ANGER DETECTED:
   Sentiment tracking: neutral → frustrated → angry
   At "frustrated": escalation warning sent to team
   At "angry": immediate escalation
   Reason logged: sentiment

5. HIGH-RISK TOPICS:
   Legal questions, financial/investment advice, medical
   → Immediate escalation with warning
   Reason logged: high_risk

AFTER ESCALATION:
  → Support queue: "Sophie — camera inquiry — URGENT"
  → Agent assigned (by availability/skill)
  → Full transcript available to agent immediately
  → Agent sees: previous conversation, visitor info, linked lead
```

### Sentiment Tracking

```
Each message analysed for sentiment:
  Message 1: "Hi, looking for cameras" → neutral
  Message 2: "What's the price?" → neutral
  Message 3: "That seems expensive" → neutral
  Message 4: "I've been waiting 10 minutes!" → frustrated ⚠️
  Message 5: "This is UNACCEPTABLE" → angry 🚨 → ESCALATE

Sentiment stored on session:
  current_sentiment: angry
  peak_sentiment: angry (highest ever in this session)
  escalation_reason: sentiment
```

---

## 16. Module 14 — `custom_helpdesk`

### Purpose
A full helpdesk ticketing system with AI classification, AI-drafted replies (pending human approval before sending), SLA tracking, customer portal, and an approval workflow ensuring AI replies are never sent without human review.

### Ticket Lifecycle

```
New → In Progress → Pending Customer → Resolved → Closed
                 ↑                ↑
         AI replies here    Human approves here
```

### Ticket Fields

```
Core:
  Subject: "Camera not working — autofocus broken"
  Customer: Sarah van den Berg
  Company: Cognita Rentals BV
  Source: Email (auto-created from incoming email)
  
Classification (AI-assigned, human can override):
  Category: Rental Issue
  Priority: High
  Sentiment: Frustrated
  Suggested assignee: Rental Support Team
  
SLA:
  SLA Policy: "Rental Complaints — 4h response"
  SLA start: 2026-06-05 10:00
  SLA response deadline: 2026-06-05 14:00
  SLA resolution deadline: 2026-06-06 10:00
  Status: Active ✅

Links:
  Linked rental order: RO-042 (Sony FX3, June 20-22)
  Linked customer: Sarah van den Berg
```

### AI Classification + Draft Reply Flow

```
TICKET CREATED (from email):
  Subject: "Camera not working properly"
  Body: "The camera I rented has broken autofocus and I cannot use
         it for my wedding shoot tomorrow. This is very frustrating."

AI ANALYSIS:
  Category suggested:   Rental Issue
  Priority suggested:   High (rental + event dependency)
  Sentiment detected:   Frustrated
  Assignee suggested:   Rental Support Team
  Risk flags:           Time-sensitive (event tomorrow)
  Missing info:         Which specific unit / serial number?

AI DRAFT REPLY (status: Pending Approval):
  "Dear Sarah,
   
   Thank you for contacting us and I sincerely apologize for the
   inconvenience with the camera autofocus.
   
   We take rental equipment issues very seriously, especially when
   you have an important event scheduled. We will arrange an
   immediate replacement unit to be delivered to you today.
   
   Could you please confirm your delivery address and availability
   for a courier this afternoon?
   
   Kind regards,
   Cognita Rentals Support"

AGENT REVIEW:
  Agent Jan reads the AI draft
  Edits: Adds "by 15:00 today" for specificity
  Edit reason: "Added concrete delivery time to reduce anxiety"
  
  The edit reason is stored immutably — used to improve AI over time.
  Agent clicks "Approve & Send"
  
  → Email sent to Sarah at 10:45 ✅
  → SLA: Response within 45 minutes (under 4h SLA) ✅
```

### SLA Management

```
SLA Policies configured:
  "Standard"      → First response: 24h, Resolution: 72h
  "High Priority" → First response: 8h,  Resolution: 24h
  "Rental Issue"  → First response: 4h,  Resolution: 12h
  "Urgent/Angry"  → First response: 1h,  Resolution: 4h

SLA breach behaviour:
  30 min before deadline: Yellow warning on ticket
  Deadline passed:        Red badge, manager notification
  Escalation:             Ticket escalated to senior agent or manager

Dashboard:
  SLA compliance this week: 92%
  Breached tickets: 2 (both in review)
  Average response time: 1h 23m
  Average resolution time: 6h 45m
```

### Customer Portal

```
URL: https://yoursite.com/helpdesk

Customer Sarah sees:
  My Tickets:
    #HD-1042  Camera autofocus issue  →  In Progress
    #HD-0998  Invoice query           →  Resolved

Clicking on ticket shows:
  Full thread (customer messages + agent replies)
  Current status and expected resolution time
  Option to add reply or attachment
  Option to mark as resolved
```

---

## 17. Module 15 — `custom_email_ai`

### Purpose
Connects a company mailbox (IMAP/SMTP or Microsoft 365) and uses AI to classify incoming emails, auto-link them to existing contacts/deals/tickets, and generate draft replies. All AI-drafted replies go into a Pending Outbox where a human must approve before sending. Auto-sending is never the default.

### Mailbox Connection

```
Supported:
  Generic IMAP/SMTP (all email providers)
  Microsoft 365 Graph API (enterprise O365 accounts)

Setup:
  Email AI → Configuration → Mailboxes → New
  Host: mail.yourcompany.nl
  Port: 993 (IMAP SSL)
  Username: info@cognita-innovative.com
  Password: [encrypted at rest]
  
  Check every: 5 minutes (configurable)
```

### Incoming Email Processing Flow

```
Email received: info@cognita-innovative.com

From: pieter@acme.nl
Subject: "Invoice INV/2026/0042 — amount discrepancy"
Body: "I received your invoice but the amount seems
       different from what we agreed. The quote was
       €15,000 but the invoice shows €18,150..."

AI PROCESSES:

1. Classification:
   Category: Finance / Invoice Query
   Priority: High (involves money, existing customer)
   Sentiment: Confused (not angry — genuine question)
   
2. Contact matching:
   pieter@acme.nl → Pieter de Vries, Acme BV ✅ (existing contact)
   
3. Record linking:
   Invoice INV/2026/0042 found ✅ (linked to Pieter)
   Quote SO/2026/0042 found ✅ (VAT 21% added = €15,000 + €3,150)
   
4. Helpdesk ticket auto-created:
   #HD-1050: "Invoice amount query — Pieter de Vries"
   Category: Billing, Priority: High
   Linked: invoice, quote, customer
   
5. AI draft reply (PENDING OUTBOX):
   "Dear Pieter,
    
    Thank you for reaching out about invoice INV/2026/0042.
    
    The difference you noticed is VAT (21%) which was added
    to the agreed net amount of €15,000:
      Net:      €15,000.00
      VAT 21%:   €3,150.00
      Total:    €18,150.00 (as shown on the invoice)
    
    This is in line with Dutch VAT regulations and was outlined
    in the quote terms. Please let me know if you have any
    further questions.
    
    Kind regards,
    Cognita Innovative Finance Team"
```

### Pending Outbox — Human Approval Workflow

```
PENDING OUTBOX (Email AI → Outbox):

┌────────────────────────────────────────────────────────┐
│ To: pieter@acme.nl                                     │
│ Re: Invoice INV/2026/0042                              │
│ Generated: 2026-06-05 11:05                            │
│ Status: PENDING APPROVAL                               │
│                                                        │
│ [Preview draft]  [Edit]  [Approve & Send]  [Reject]    │
│                                                        │
│ Reject reason: ___________________  [Save]             │
└────────────────────────────────────────────────────────┘

Finance manager opens, reads, approves:
  → Email sent to Pieter
  → Ticket updated with sent reply
  → Audit log: sent at 11:12 by user:maria

If rejected:
  Reason: "Needs director approval before responding"
  → Status: Rejected — Needs Info
  → Assigned to director for revised reply

AUTO-SEND RULE (disabled by default):
  Can be enabled ONLY for specific low-risk categories:
    "Order acknowledgement" → auto-send after 2h if no agent review
  This requires explicit admin configuration and is never the default.
```

---

## 18. Module 16 — `custom_whatsapp_social`

### Purpose
Manages WhatsApp messaging and multi-channel social media (Instagram, Facebook, LinkedIn, X/Twitter) from a unified inbox. Includes an AI content calendar for planning and scheduling social media posts.

### WhatsApp Messaging Flow

```
INBOUND WHATSAPP:
  Caller: +31 6 12345678
  Message: "Hoi, is de Sony FX3 beschikbaar voor aanstaand weekend?"

SYSTEM PROCESSES:
  Phone lookup: +31612345678 → Sarah van den Berg ✅ (existing contact)
  Previous conversations: 2 rentals, Gold customer
  
  Context provided to AI:
    Customer: Sarah, Gold tier, 2 previous rentals
    Message: availability query for this weekend
    
  AI DRAFT (PENDING):
    "Hoi Sarah! Ja, de Sony FX3 is dit weekend beschikbaar.
     Prijs: €300 (weekend tarief) + €1.000 borg.
     Wil je dat ik een offerte maak?"

AGENT APPROVES → MESSAGE SENT

Sarah replies:
  "Ja graag! Vrijdag ophalen, maandag terug."
  
Agent handles conversation directly → Rental quote created from chat.
```

### Social Media Unified Inbox

```
ALL channels in one view:
  WhatsApp:   3 new messages
  Instagram:  1 new comment (on camera photo)
  Facebook:   2 new messages
  LinkedIn:   0 new messages

Instagram comment:
  Photo: "Sony FX3 rental available"
  Comment by: @sophie.lens.photography
  "Is this available for hire? What's the price?"
  
  AI Draft reply:
    "Hi Sophie! Yes available for rental, €150/day.
     DM us or visit our website to book! 📸"
  
  Agent approves → Reply posted to Instagram ✅
```

### Post Calendar & Content Planning

```
CONTENT CALENDAR — June 2026:

June 10 (Tuesday):
  Topic: "New arrivals — Camera Equipment"
  Channels: Instagram, Facebook, LinkedIn
  AI Generated caption:
    "📸 New in stock: Sony FX3 Professional Kit.
     Perfect for weddings, events & commercial shoots.
     Available from €150/day. Book now! [link]"
  Status: Draft → Agent approved → Scheduled 09:00

June 15 (Sunday):
  Topic: "Weekend special — 10% off"
  Channels: Instagram, Facebook
  Status: Pending approval

Recurring topics (configured):
  Every Monday: "Week availability update"
  Every Friday: "Weekend rental special offer"
  First of month: "New products and promotions"

AI GENERATES post text for all topics.
AGENT APPROVES every post before scheduling.
SYSTEM PUBLISHES at scheduled time (where API permits).
```

### External Approval Blockers

```
⚠️  Meta WhatsApp Cloud API:
    → Wired and ready in code
    → Uses mock/sandbox until Meta Business App Review approved
    → Submit at: business.facebook.com → WhatsApp → Get Started

⚠️  Meta Graph API (Instagram/Facebook posting):
    → Wired and ready
    → Requires Meta app review for publishing permissions
    → Submit at: developers.facebook.com

⚠️  X/Twitter API:
    → Wired and ready (mock)
    → Requires paid API tier for posting
    → Sign up at: developer.twitter.com
```

---

## 19. Module 17 — `custom_ai_voice`

### Purpose
Handles inbound phone calls with an AI voice agent. Incoming calls trigger a TwiML webhook, the AI greets the caller, answers questions using the RAG knowledge base (via speech-to-text and text-to-speech), tracks caller sentiment, escalates to a human agent when needed, and creates transcripts, summaries, and linked CRM/helpdesk records.

### Call Flow Architecture

```
Incoming call → Twilio (or SIP) → Webhook → Platform
→ AI greets caller
→ STT: caller speech converted to text
→ RAG: text searched against knowledge base
→ AI: generates response
→ TTS: response spoken back to caller
→ Loop until resolved, escalated, or ended
```

### Sentiment Tracking During Call

```
Sentiment levels (ordered by severity):
  calm / positive: escalation score 0
  neutral:         escalation score 1
  confused:        escalation score 2
  frustrated:      escalation score 3
  urgent:          escalation score 4
  angry:           escalation score 5

Peak sentiment tracked (never goes down during a call):
  Start: neutral
  "I called three times already!" → frustrated (score 3)
  "I want to CANCEL everything!" → angry (score 5) → ESCALATE

Escalation threshold (configurable per call flow):
  Default: escalate at frustrated (score 3) or higher
```

### Full Call Example — Rental Support

```
INCOMING CALL: +31 20 123 4567

[Webhook triggered: /voice/incoming/2]
[Call flow: "Rental Support"]

AI GREETING (TTS, ElevenLabs voice):
  "Welcome to Cognita Rentals. I'm your AI assistant.
   How can I help you today?"

CALLER (STT → Deepgram transcribes):
  "I'd like to check if the Sony FX3 camera is available
   next weekend, the 27th and 28th of June."

RAG SEARCH:
  Query: "Sony FX3 availability June 27-28"
  Searches: rental calendar + product catalog
  Result: FX3 unit 2 available June 27-28 ✅

AI RESPONSE (TTS):
  "Great news! The Sony FX3 Professional Kit is available
   for the weekend of June 27th and 28th. The weekend rate
   is €300, plus a €1,000 refundable deposit.
   Would you like me to create a reservation?"

CALLER:
  "Yes please. My name is Thomas Bakker."

AI:
  "Thank you Thomas. I'll note your interest and have one of
   our team contact you to complete the booking. Could you
   confirm your phone number or email?"

CALLER:
  "thomas@bakker.nl"

→ CRM Lead auto-created:
    Name: Thomas Bakker
    Email: thomas@bakker.nl
    Source: AI Voice Call
    Interest: FX3 Kit rental June 27-28
    
→ Follow-up task for sales team:
    "Call back Thomas — FX3 rental inquiry — ASAP"

→ Call summary (AI generated):
    "Caller inquired about Sony FX3 availability for June 27-28
     weekend. Confirmed available. Lead captured. Callback needed
     to complete booking. Caller was calm and cooperative."

→ Sentiment: positive throughout ✅
→ No escalation needed
```

### Escalation Example — Angry Caller

```
INCOMING CALL: returning rental customer, complaint

AI: "Welcome to Cognita Rentals, how can I help?"
Caller: "I returned the camera YESTERDAY and still no deposit refund!"

AI: "I understand your concern about the deposit. Let me check..."
[Sentiment: frustrated — escalation warning]

Caller: "I've called THREE TIMES! This is absolutely RIDICULOUS!
         I want my money back NOW or I'm disputing the charge!"

[Sentiment: angry — ESCALATE IMMEDIATELY]

AI: "I completely understand your frustration and I sincerely
     apologise for this delay. I'm transferring you immediately
     to our senior support team who can resolve this right now."

→ Human agent receives:
    Notification: "URGENT — Angry customer — deposit dispute"
    Call transferred with context:
      Customer: Sarah van den Berg (Gold tier)
      Rental: RO-042, returned June 22
      Issue: Deposit refund not received
      Sentiment history: neutral → frustrated → angry
      Summary: "Customer very frustrated about deposit delay,
                threatening chargeback. Handle with priority."

→ Senior agent takes the call with full context
→ Issue resolved: deposit processed immediately
→ Ticket created for follow-up and process review
```

### Call Transcript & Records

```
Every call records:
  Full transcript (line by line with timestamps and speaker)
  AI-generated summary
  Sentiment journey (per message)
  Peak sentiment level
  Call outcome: resolved / transferred / callback / missed
  Duration
  Recording URL (only if consent given + configured)

Legal note on call recording:
  Recording consent required before recording starts
  Two-party consent required in Netherlands and most EU jurisdictions
  Recording is disabled by default
  Must be explicitly enabled per call flow + per jurisdiction config
```

---

## 20. End-to-End Business Flows

### Flow A — Sales to Cash (Complete)

```
TRIGGER: Customer visits website and asks about software

1. [custom_ai_chatbot]
   Visitor asks about "ERP software for small business"
   AI answers from knowledge base (RAG)
   "Would you like to schedule a demo?"
   Visitor: "Yes — Sarah Johnson, sarah@startupco.nl"
   → CRM Lead created: Sarah Johnson, Website Chat, €0

2. [custom_crm_core]
   Lead assigned to salesperson Jan
   AI lead score: 65/100 (email present, website visit)
   Activity: "Call Sarah within 24h"
   Jan calls Sarah → meeting scheduled

3. [custom_planning]
   Demo appointment created: June 10, 14:00
   Confirmation email sent to Sarah
   Reminder to Jan: June 10 13:00

4. [custom_crm_core]
   Demo held → Deal created: "StartupCo — Full Platform"
   Stage: Proposal
   Expected revenue: €15,000
   Probability: 60%

5. [custom_quote_signing]
   Quote created: Software €10,000 + Support €5,000 = €15,000
   Sent for signing → Sarah opens portal
   Sarah accepts terms and signs
   Deal: WON ✅
   Document hash: stored immutably

6. [custom_planning]
   Auto-job: "Platform Implementation — StartupCo"
   Assigned: Jan + Thomas
   Date: June 20-21

7. [custom_inventory]
   Software licenses reserved (if physical product: stock deducted)

8. [custom_accounting_basic]
   Invoice: INV/2026/0050 → €18,150 (incl. 21% VAT)
   Invoice emailed to Sarah

9. [custom_accounting_basic]
   Bank statement imported: +€18,150 from StartupCo
   AI match: 98% confidence → Invoice INV/2026/0050
   One-click reconcile ✅
   Invoice: Paid ✅

10. [custom_accounting_advanced]
    Revenue recognised: €15,000 (net)
    Journal entry posted
    P&L updated
    Budget vs actual: Sales Q2 on track ✅
```

### Flow B — Rental Business (Complete)

```
TRIGGER: Phone call enquiry about camera rental

1. [custom_ai_voice]
   Incoming call answered by AI
   Caller: "Sony FX3 available June 27-28?"
   AI checks availability: YES
   Lead captured: Thomas Bakker, thomas@bakker.nl

2. [custom_crm_core]
   Lead: Thomas Bakker, Source: AI Voice
   Salesperson Jan follows up → Rental quote created

3. [custom_rental]
   Rental quote:
     FX3 Kit, June 27-28 (weekend)
     Price: €300 + €15 deposit top-up + €25 cleaning
     Deposit: €1,000

4. [custom_quote_signing]
   Thomas signs online → audit evidence stored
   Availability: June 27-28 RESERVED

5. [custom_rental]
   ID verification: Thomas Bakker, BSN last-4: 1234, risk: Low
   Deposit: €1,000 received June 27

6. [custom_inventory]
   Stock: FX3 Unit 2 → Active rental (reserved from other bookings)

7. [custom_planning]
   Jobs auto-created:
     "Rental Pickup — Thomas — June 27 14:00"
     "Rental Return — Thomas — June 28 18:00"

8. [custom_rental]
   Return June 28: all good, no damage ✅
   Deposit: €1,000 full refund

9. [custom_accounting_basic]
   Invoice: €300 (rental) + €25 (cleaning) = €325 + VAT
   Deposit: €1,000 refunded

10. [custom_inventory]
    FX3 Unit 2: Available again ✅
```

### Flow C — HR & Payroll (Complete)

```
TRIGGER: New employee hired

1. [custom_hrm]
   Employee created: Thomas Bakker, EMP-0043
   Onboarding checklist auto-triggered
   Portal access granted (login credentials emailed)

2. [Portal — Employee]
   Thomas logs in to portal
   Completes profile: address, emergency contact, bank details
   Signs employment contract (HR portal doc signing)

3. [custom_hrm]
   Leave balance set: 20 days annual leave
   Thomas requests first week of vacation (Sept 1-5)
   Manager Jan approves → balance: 20 → 15 days

4. [Month-end: custom_payroll_nl]
   Payroll run: September 2026
   Thomas: Gross €3,000, 40h/week, LHK: Yes
   
   Calculated:
     Gross:        €3,000
     Loonheffing: -€  650
     Pension (4%): -€  120
     Net:          €2,230
   
   Employer cost: €3,350 (incl. AWF, ZVW, pension 6%)
   Vakantiegeld accrual: €240

5. [custom_hrm — Portal]
   Payslip published: Thomas sees September payslip
   Downloads PDF

6. [custom_accounting_basic]
   Journal entry: Wage expense Dr, Salary payable Cr

7. [Export]
   CSV exported → accountant files loonaangifte
```

### Flow D — AI Support Cycle (Complete)

```
TRIGGER: Customer email complaint

1. [custom_email_ai]
   Email from Sarah: "Camera had broken autofocus!"
   AI: classifies as Rental Complaint, High priority
   Links to: rental RO-042, customer Sarah

2. [custom_helpdesk]
   Ticket auto-created: #HD-1042
   Category: Rental Issue, Priority: High
   SLA: 4h response, 12h resolution
   AI draft reply: PENDING APPROVAL

3. [Agent review]
   Agent reads AI draft
   Edits: adds "replacement within 2 hours"
   Reason stored: "Added concrete ETA to reassure customer"
   Approves → Email sent (45 min after ticket creation ✅)

4. [Resolution]
   Replacement camera dispatched
   Planning job: "Emergency delivery — Sarah — FX3 replacement"
   Customer confirms satisfied

5. [Ticket closed]
   Resolution time: 3h 20m (under 12h SLA ✅)
   Edit reason stored → AI improvement queue

6. [Follow-up]
   AI improvement record:
     Original AI draft: no specific ETA
     Human addition: "within 2 hours"
     Category: Response specificity
     → Next time AI drafts rental complaints: include time commitment
```

---

## 21. Role & Access Matrix

| Role | Modules | Access Level |
|---|---|---|
| **Company Admin** | All modules | Full — configure everything |
| **AI Admin** | AI Core, Chatbot, Voice | Manage providers, RAG docs, flows |
| **Sales Manager** | CRM, Quote Signing, Planning | Full + approve discounts |
| **Sales Rep** | CRM, Quote Signing, Planning | Own leads/deals only |
| **Finance Manager** | Accounting Basic+Advanced, Payroll | Full financial access |
| **Accountant** | Accounting Basic+Advanced | View + post (no payroll) |
| **HR Manager** | HRM, Payroll NL | All employees + payroll |
| **Payroll Manager** | Payroll NL | Payroll runs + payslips |
| **Employee (portal)** | Portal only | Own profile, leaves, payslips |
| **Inventory Manager** | Inventory | Full stock management |
| **Rental Manager** | Rental, Inventory | Full rental + stock |
| **Support Manager** | Helpdesk, Email AI, WhatsApp, Voice | Full + SLA management |
| **Support Agent** | Helpdesk, Email AI, WhatsApp | Assigned tickets only |
| **Social Media Manager** | WhatsApp Social | Posts + inbox |
| **Portal Customer** | Customer portal | Own quotes, tickets, payslips |

---

## 22. API Reference

### Odoo JSON-RPC API (All Models)

All custom models are accessible via Odoo's standard JSON-RPC endpoint.

**Authentication:**
```
POST /web/session/authenticate
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "db": "platform_dev",
    "login": "admin",
    "password": "admin"
  }
}
```

**Read Records:**
```
POST /web/dataset/call_kw
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "model": "crm.lead",
    "method": "search_read",
    "args": [[["type", "=", "opportunity"]]],
    "kwargs": {
      "fields": ["name", "email_from", "lead_score", "probability"],
      "limit": 50
    }
  }
}
```

**Available Custom Models via API:**

| Model | Description |
|---|---|
| `platform.subscription` | Module subscriptions |
| `crm.lead` | CRM leads and deals |
| `quote.signing` | Signing audit records |
| `account.bank.statement.line` | Bank transactions |
| `account.fixed.asset` | Fixed assets |
| `hr.employee` | Employees |
| `hr.payroll.payslip` | Payslips |
| `hr.payroll.run` | Payroll runs |
| `rental.order` | Rental orders |
| `planning.job` | Planning jobs |
| `chat.session` | Chatbot sessions |
| `helpdesk.ticket` | Support tickets |
| `pending.outbox` | Email AI outbox |
| `whatsapp.message` | WhatsApp messages |
| `social.post` | Social media posts |
| `voice.call` | Voice calls |
| `ai.audit.log` | AI audit records |

### Custom Webhook Endpoints

| Method | URL | Purpose |
|---|---|---|
| `POST` | `/chatbot/config` | Get chatbot configuration |
| `POST` | `/chatbot/start` | Start a chat session |
| `POST` | `/chatbot/message` | Send a message and get AI reply |
| `POST` | `/chatbot/consent` | Submit tracking consent |
| `POST` | `/chatbot/email` | Capture visitor email |
| `POST` | `/voice/incoming/<flow_id>` | Inbound VoIP call (TwiML) |
| `POST` | `/voice/speech/<call_id>` | Process caller speech |
| `POST` | `/voice/status/<call_id>` | Call status callback |
| `POST` | `/voice/mock/call/<flow_id>` | Test voice flow |
| `POST` | `/whatsapp/webhook/<provider_id>` | WhatsApp inbound webhook |
| `POST` | `/social/webhook/<channel_id>` | Social media webhook |
| `GET` | `/quote/<token>` | Customer signing portal |
| `POST` | `/quote/<token>/sign` | Submit signature |
| `GET` | `/web/platform/brand.css` | Dynamic brand CSS |

---

*Document version 1.0 — Generated June 2026*  
*Platform: Cognita Innovative ERP on Odoo 19 Community*  
*All 17 modules — 285/285 tests passing*
