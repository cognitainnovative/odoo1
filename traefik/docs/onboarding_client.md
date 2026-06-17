# Client Onboarding Guide

## Platform Overview

This platform is a modular commercial ERP/CRM built on Odoo 19 Community. Each module can be independently licensed and activated per company.

## Quick Start (5 minutes)

### 1. First Login

Navigate to `http://your-server:8070` and log in with the admin credentials provided by your implementation team.

### 2. Configure Your Company

Go to **Settings → Companies** and:
- Set your company name, logo, and address
- Add your **loonheffingsnummer** (Payroll NL tab)
- Configure brand colors (Branding tab)
- Enable/disable external AI (AI Settings tab)

### 3. Activate Your Modules

Go to **Platform → Subscriptions** to activate the modules included in your package:

| Module | What it does |
|---|---|
| CRM Base | Leads, deals, quotes, pipeline |
| Finance Basic | Invoicing, bank import, payment matching |
| Finance Advanced | Fixed assets, BV annual accounts, budgets |
| HRM | Employee database, leave management, portal |
| Payroll NL | Dutch payroll calculations and payslips |
| Inventory | Products, stock, purchase orders |
| Rental | Full rental workflow with pricing tiers |
| Planning | Jobs, appointments, calendar |
| AI Chat | Website chatbot with RAG knowledge base |
| AI Voice | VoIP call flow with AI assistant |
| Helpdesk | Tickets, SLA, AI-assisted replies |
| Social Media | WhatsApp, social inbox, post calendar |

### 4. Configure AI

Go to **AI Platform → Configuration → Providers** and:
- The **Mock provider** is active by default (no real API calls)
- Add an **Anthropic API key** for Claude (recommended for high-quality drafts)
- Add an **Ollama** installation for fully local/private AI
- Toggle **Allow External AI** per company for data sovereignty

### 5. Import Your First Data

- **Contacts**: Accounting → Customers → Import CSV
- **Products**: Inventory → Products → Import
- **Bank statements**: Accounting → Import Bank Statement (CSV/MT940/CAMT.053)

---

## Key Workflows

### Sales → Cash
1. Create lead in **CRM**
2. Convert to deal → create quote
3. Customer signs via **signing portal** (`/quote/<token>`)
4. Quote confirmed → **Planning job** auto-created
5. Invoice generated → payment matched in **Bank reconciliation**

### Rental
1. Create rental product in **Rental → Configuration**
2. Customer books via quote → signs → pays deposit
3. Pickup recorded → stock deducted
4. Return inspection → final invoice → deposit release

### HR & Payroll
1. Add employee in **Employees**
2. Fill in **Payroll NL** tab (gross salary, LHK, pension %)
3. Run monthly payroll in **Payroll NL → Payroll Runs**
4. Approve → publish payslips to employee portal

---

## Legal Blockers (External Approvals Required)

The following features are wired but require external approval before going live:

| Feature | Blocker | Status |
|---|---|---|
| Meta WhatsApp Cloud API | Meta Business App Review | ⏳ Submit at meta.com/business |
| Facebook/Instagram posting | Meta Graph API review | ⏳ Submit at developers.facebook.com |
| X/Twitter posting | X API paid tier | ⏳ Sign up at developer.twitter.com |
| Dutch payroll filing (loonaangifte) | Certified Belastingdienst route | ⏳ Contact payroll provider |
| eIDAS qualified signatures | QTSP integration | ⏳ Contact qualified trust service provider |

---

## Support

For technical support, contact your implementation team or raise a ticket in **Helpdesk**.

For bugs, use the support email provided in your contract.
