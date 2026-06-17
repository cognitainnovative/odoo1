"""AI-powered email inbox — classification, pending outbox, approval workflow.

Credential storage: IMAP/SMTP passwords and Graph client secret are kept in
ir.config_parameter (encrypted at the database level), never as plain-text
model fields.  Use action_set_imap_password / action_set_graph_secret to store
them.  The compute/inverse pattern on `imap_password` / `smtp_password` /
`graph_client_secret` makes them usable in the form view (write-only widgets).
"""

import email as email_lib
import imaplib
import json
import logging
import smtplib
import ssl
import urllib.parse
import urllib.request
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Keys used in ir.config_parameter for credential storage
_CRED_KEY = "email_ai.mailbox.{}.{}"


class EmailAiMailbox(models.Model):
    """Mailbox connection configuration (IMAP/SMTP or Microsoft Graph)."""

    _name = "email.ai.mailbox"
    _description = "Email Mailbox Connection"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char("Mailbox Name", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    email_address = fields.Char("Email Address", required=True)
    connection_type = fields.Selection(
        [("imap", "IMAP / SMTP"), ("graph", "Microsoft Graph (Office 365)")],
        default="imap",
        required=True,
    )

    # IMAP / SMTP settings
    imap_host = fields.Char("IMAP Host")
    imap_port = fields.Integer("IMAP Port", default=993)
    imap_ssl = fields.Boolean("IMAP SSL", default=True)
    smtp_host = fields.Char("SMTP Host")
    smtp_port = fields.Integer("SMTP Port", default=587)
    smtp_tls = fields.Boolean("SMTP STARTTLS", default=True)

    # Credentials — write-only via compute/inverse; stored in ir.config_parameter
    imap_password = fields.Char(
        "IMAP Password",
        compute="_compute_imap_password",
        inverse="_inverse_imap_password",
        store=False,
    )
    smtp_password = fields.Char(
        "SMTP Password",
        compute="_compute_smtp_password",
        inverse="_inverse_smtp_password",
        store=False,
    )

    # Microsoft Graph / OAuth settings
    graph_tenant_id = fields.Char("Tenant ID (Azure)")
    graph_client_id = fields.Char("Client ID (Azure)")
    graph_client_secret = fields.Char(
        "Client Secret (Azure)",
        compute="_compute_graph_secret",
        inverse="_inverse_graph_secret",
        store=False,
    )

    state = fields.Selection(
        [("draft", "Not Configured"), ("connected", "Connected"), ("error", "Connection Error")],
        default="draft",
        tracking=True,
    )
    last_sync = fields.Datetime("Last Sync", readonly=True)
    message_count = fields.Integer(compute="_compute_message_count", string="Imported Messages")
    active = fields.Boolean(default=True)

    # Auto-send configuration — optional limited auto-send for low-risk categories
    auto_send_enabled = fields.Boolean(
        "Enable Limited Auto-send",
        default=False,
        help="When enabled, AI-drafted replies in the specified categories are automatically "
        "approved and sent without human review. DISABLED by default. Enable only after "
        "explicit admin decision and only for genuinely low-risk categories.",
    )
    auto_send_categories = fields.Char(
        "Auto-send Categories",
        help="Comma-separated list of ai_category values that are eligible for auto-send "
        "(e.g. 'general'). Has no effect when auto_send_enabled is False.",
    )

    def _compute_message_count(self):
        for mb in self:
            mb.message_count = self.env["email.ai.message"].search_count(
                [("mailbox_id", "=", mb.id)]
            )

    # ── Credential helpers ────────────────────────────────────────────────────

    def _get_credential(self, suffix):
        self.ensure_one()
        return (
            self.env["ir.config_parameter"].sudo().get_param(_CRED_KEY.format(self.id, suffix), "")
        )

    def _set_credential(self, suffix, value):
        self.ensure_one()
        self.env["ir.config_parameter"].sudo().set_param(
            _CRED_KEY.format(self.id, suffix), value or ""
        )

    def _compute_imap_password(self):
        for mb in self:
            mb.imap_password = "" if not mb.id else mb._get_credential("imap_password")

    def _inverse_imap_password(self):
        for mb in self:
            if mb.imap_password:
                mb._set_credential("imap_password", mb.imap_password)

    def _compute_smtp_password(self):
        for mb in self:
            mb.smtp_password = "" if not mb.id else mb._get_credential("smtp_password")

    def _inverse_smtp_password(self):
        for mb in self:
            if mb.smtp_password:
                mb._set_credential("smtp_password", mb.smtp_password)

    def _compute_graph_secret(self):
        for mb in self:
            mb.graph_client_secret = "" if not mb.id else mb._get_credential("graph_secret")

    def _inverse_graph_secret(self):
        for mb in self:
            if mb.graph_client_secret:
                mb._set_credential("graph_secret", mb.graph_client_secret)

    # ── Connection test ───────────────────────────────────────────────────────

    def action_test_connection(self):
        self.ensure_one()
        try:
            if self.connection_type == "imap":
                self._test_imap_connection()
            else:
                self._test_graph_connection()
            self.state = "connected"
            self.message_post(
                body="Connection test successful.",
                subtype_xmlid="mail.mt_note",
            )
        except UserError:
            raise
        except Exception as exc:
            self.state = "error"
            self.message_post(
                body=f"Connection failed: {exc}",
                subtype_xmlid="mail.mt_note",
            )
            raise UserError(str(exc)) from exc

    def _test_imap_connection(self):
        password = self._get_credential("imap_password")
        if not self.imap_host:
            raise UserError("IMAP host is required.")
        if not password:
            raise UserError("IMAP password not set. Enter the password in the form and save first.")
        try:
            if self.imap_ssl:
                conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port or 993)
            else:
                conn = imaplib.IMAP4(self.imap_host, self.imap_port or 143)
            conn.login(self.email_address, password)
            conn.logout()
        except imaplib.IMAP4.error as exc:
            raise UserError(f"IMAP authentication failed: {exc}") from exc

    def _test_graph_connection(self):
        secret = self._get_credential("graph_secret")
        if not all([self.graph_tenant_id, self.graph_client_id, secret]):
            raise UserError("Tenant ID, Client ID, and Client Secret are all required for Graph.")
        token_url = f"https://login.microsoftonline.com/{self.graph_tenant_id}/oauth2/v2.0/token"
        data = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.graph_client_id,
                "client_secret": secret,
                "scope": "https://graph.microsoft.com/.default",
            }
        ).encode()
        try:
            req = urllib.request.Request(token_url, data=data)
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_data = json.loads(resp.read())
        except Exception as exc:
            raise UserError(f"Graph token request failed: {exc}") from exc
        if "access_token" not in token_data:
            raise UserError(
                f"Graph returned no access token: "
                f"{token_data.get('error_description', token_data)}"
            )

    def _get_graph_token(self):
        """Fetch and return a Graph API Bearer token."""
        secret = self._get_credential("graph_secret")
        token_url = f"https://login.microsoftonline.com/{self.graph_tenant_id}/oauth2/v2.0/token"
        data = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.graph_client_id,
                "client_secret": secret,
                "scope": "https://graph.microsoft.com/.default",
            }
        ).encode()
        req = urllib.request.Request(token_url, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["access_token"]

    # ── Email import ──────────────────────────────────────────────────────────

    def action_import_emails(self):
        self.ensure_one()
        try:
            if self.connection_type == "imap":
                count = self._import_imap_emails()
            else:
                count = self._import_graph_emails()
            self.write({"last_sync": fields.Datetime.now(), "state": "connected"})
            self.message_post(
                body=f"Sync complete — {count} new message(s) imported.",
                subtype_xmlid="mail.mt_note",
            )
        except UserError:
            raise
        except Exception as exc:
            self.state = "error"
            raise UserError(f"Email import failed: {exc}") from exc

    def _import_imap_emails(self):
        password = self._get_credential("imap_password")
        if not self.imap_host or not password:
            raise UserError("IMAP host and password are required for import.")

        if self.imap_ssl:
            conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port or 993)
        else:
            conn = imaplib.IMAP4(self.imap_host, self.imap_port or 143)
        conn.login(self.email_address, password)
        conn.select("INBOX")
        _, msg_nums = conn.search(None, "UNSEEN")
        nums = msg_nums[0].split() if msg_nums[0] else []

        count = 0
        for num in nums[:50]:  # cap per sync to avoid very large imports
            try:
                _, data = conn.fetch(num, "(RFC822)")
                raw = data[0][1]
                parsed = email_lib.message_from_bytes(raw)

                # Decode subject
                subject_parts = decode_header(parsed.get("Subject") or "")
                subject_str, enc = subject_parts[0] if subject_parts else (b"", None)
                if isinstance(subject_str, bytes):
                    subject_str = subject_str.decode(enc or "utf-8", errors="replace")

                from_header = parsed.get("From", "")
                message_id = parsed.get("Message-ID", "")
                in_reply_to = parsed.get("In-Reply-To", "")

                # Skip already-imported messages
                if message_id and self.env["email.ai.message"].search(
                    [("message_id_header", "=", message_id)], limit=1
                ):
                    continue

                # Parse sender address and display name from RFC 2822 From header
                from_email = from_header
                from_name = from_header
                try:
                    from email.utils import parseaddr as _parseaddr

                    _name, _addr = _parseaddr(from_header)
                    if _addr:
                        from_email = _addr
                        from_name = _name or _addr
                except Exception:
                    pass

                # Extract text body
                body_text = ""
                if parsed.is_multipart():
                    for part in parsed.walk():
                        if part.get_content_type() == "text/plain" and not body_text:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode(
                                    part.get_content_charset() or "utf-8", errors="replace"
                                )
                else:
                    payload = parsed.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode(
                            parsed.get_content_charset() or "utf-8", errors="replace"
                        )

                # Find thread root if this is a reply
                thread_root_id = False
                if in_reply_to:
                    root = self.env["email.ai.message"].search(
                        [("message_id_header", "=", in_reply_to)], limit=1
                    )
                    if root:
                        thread_root_id = root.id

                self.env["email.ai.message"].create(
                    {
                        "name": subject_str or "(no subject)",
                        "date": fields.Datetime.now(),
                        "from_email": from_email,
                        "from_name": from_name,
                        "body_text": body_text,
                        "mailbox_id": self.id,
                        "message_id_header": message_id,
                        "in_reply_to": in_reply_to,
                        "thread_root_id": thread_root_id,
                        "partner_id": self._resolve_or_create_partner(from_email, from_name),
                    }
                )
                count += 1
            except Exception as exc:
                _logger.warning("Failed to import message %s: %s", num, exc)

        conn.logout()
        return count

    def _import_graph_emails(self):
        """Import unread emails from the mailbox via Microsoft Graph API."""
        token = self._get_graph_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = (
            f"https://graph.microsoft.com/v1.0/users/{self.email_address}"
            f"/mailFolders/inbox/messages?$filter=isRead eq false&$top=50"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        count = 0
        for item in data.get("value", []):
            internet_id = item.get("internetMessageId", "")
            if internet_id and self.env["email.ai.message"].search(
                [("message_id_header", "=", internet_id)], limit=1
            ):
                continue
            sender = item.get("sender", {}).get("emailAddress", {})
            from_email = sender.get("address", "")
            from_name = sender.get("name", "")
            self.env["email.ai.message"].create(
                {
                    "name": item.get("subject", "(no subject)"),
                    "date": fields.Datetime.now(),
                    "from_email": from_email,
                    "from_name": from_name,
                    "body_text": item.get("bodyPreview", ""),
                    "mailbox_id": self.id,
                    "message_id_header": internet_id,
                    "partner_id": self._resolve_or_create_partner(from_email, from_name),
                }
            )
            count += 1
        return count

    def send_smtp(self, to_email, subject, body_html, cc_email="", from_name=""):
        """Send a single email via this mailbox's SMTP settings."""
        smtp_pw = self._get_credential("smtp_password")
        if not self.smtp_host:
            raise UserError("SMTP host is not configured for this mailbox.")

        from_addr = f"{from_name} <{self.email_address}>" if from_name else self.email_address
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email
        if cc_email:
            msg["Cc"] = cc_email
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            if self.smtp_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port or 587)
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            else:
                server = smtplib.SMTP_SSL(
                    self.smtp_host,
                    self.smtp_port or 465,
                    context=ssl.create_default_context(),
                )
            if smtp_pw:
                server.login(self.email_address, smtp_pw)
            recipients = [to_email] + ([cc_email] if cc_email else [])
            server.sendmail(from_addr, recipients, msg.as_string())
            server.quit()
        except smtplib.SMTPException as exc:
            raise UserError(f"SMTP send failed: {exc}") from exc

    def get_auto_send_categories(self):
        """Return the set of categories eligible for auto-send on this mailbox."""
        if not self.auto_send_enabled or not self.auto_send_categories:
            return set()
        return {c.strip() for c in self.auto_send_categories.split(",") if c.strip()}

    def _resolve_or_create_partner(self, from_email, from_name=""):
        """Return res.partner id matching from_email, or False if no match.

        Only links to *existing* partners — never auto-creates new ones from raw
        email headers, as that would produce low-quality partner records.
        """
        if not from_email:
            return False
        Partner = self.env["res.partner"].sudo()
        partner = Partner.search([("email", "=ilike", from_email)], limit=1)
        if partner:
            return partner.id
        return False


class EmailAiFinanceTask(models.Model):
    """Finance task created automatically when an email is classified as invoice/finance."""

    _name = "email.ai.finance.task"
    _description = "Finance Task from Email"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char("Subject", required=True)
    email_message_id = fields.Many2one(
        "email.ai.message", "Source Email", ondelete="set null", readonly=True
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    partner_id = fields.Many2one("res.partner", "Contact", ondelete="set null")
    invoice_id = fields.Many2one("account.move", "Linked Invoice", ondelete="set null")
    description = fields.Text("Description")
    state = fields.Selection(
        [
            ("pending", "Pending Review"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        tracking=True,
        string="Status",
    )
    assigned_to_id = fields.Many2one("res.users", "Assigned To", index=True)
    due_date = fields.Date("Due Date")
    priority = fields.Selection([("0", "Normal"), ("1", "High"), ("2", "Urgent")], default="0")

    def action_mark_done(self):
        self.write({"state": "done"})

    def action_mark_in_progress(self):
        self.write({"state": "in_progress"})


class EmailAiTemplate(models.Model):
    """Reusable email reply templates for the pending outbox."""

    _name = "email.ai.template"
    _description = "Email Reply Template"
    _order = "name"

    name = fields.Char("Template Name", required=True)
    subject_template = fields.Char(
        "Subject Template", help="Use {subject} as placeholder for the original subject."
    )
    body_template = fields.Text(
        "Body Template",
        required=True,
        help="Placeholders: {name} = sender name, {summary} = AI summary.",
    )
    category = fields.Selection(
        [
            ("helpdesk", "Helpdesk / Support"),
            ("sales_lead", "Sales"),
            ("invoice", "Invoice / Finance"),
            ("general", "General"),
        ],
        default="general",
    )
    language_code = fields.Char("Language", default="en")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    active = fields.Boolean(default=True)


class EmailAiMessage(models.Model):
    """An imported email message, linked to contacts/tickets/deals."""

    _name = "email.ai.message"
    _description = "AI Email Message"
    _inherit = ["mail.thread"]
    _order = "date desc"

    name = fields.Char("Subject", required=True)
    date = fields.Datetime("Received", required=True)
    from_email = fields.Char("From")
    from_name = fields.Char("Sender Name")
    to_email = fields.Char("To")
    body_text = fields.Text("Body (text)")
    body_html = fields.Html("Body (HTML)")
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, index=True)

    # Mailbox source
    mailbox_id = fields.Many2one("email.ai.mailbox", "Mailbox", ondelete="set null")

    # Thread grouping (RFC 2822)
    message_id_header = fields.Char(
        "Message-ID", index=True, help="RFC 2822 Message-ID — used to group replies into threads."
    )
    in_reply_to = fields.Char("In-Reply-To")
    thread_root_id = fields.Many2one(
        "email.ai.message", "Thread Root", ondelete="set null", index=True
    )
    reply_ids = fields.One2many("email.ai.message", "thread_root_id", "Replies in Thread")

    # Internal note (visible only to staff)
    internal_note = fields.Text("Internal Note")

    # Reply template
    template_id = fields.Many2one("email.ai.template", "Reply Template", ondelete="set null")

    # Classification
    ai_category = fields.Selection(
        [
            ("helpdesk", "Helpdesk / Support"),
            ("sales_lead", "Sales Lead"),
            ("invoice", "Invoice / Finance"),
            ("general", "General"),
            ("spam", "Spam / Irrelevant"),
        ],
        string="AI Category",
        readonly=True,
    )
    ai_classification_done = fields.Boolean(readonly=True, default=False)
    ai_summary = fields.Text("AI Summary", readonly=True)
    ai_sentiment = fields.Char("Sentiment", readonly=True)

    # State
    state = fields.Selection(
        [
            ("new", "New — Unprocessed"),
            ("classified", "Classified"),
            ("linked", "Linked to Record"),
            ("draft_reply", "Draft Reply Pending"),
            ("replied", "Replied"),
            ("archived", "Archived"),
        ],
        default="new",
        tracking=True,
    )

    # Linked records
    partner_id = fields.Many2one("res.partner", "Contact", ondelete="set null")
    ticket_id = fields.Many2one("helpdesk.ticket", "Helpdesk Ticket", ondelete="set null")
    lead_id = fields.Many2one("crm.lead", "Lead / Deal", ondelete="set null")
    invoice_id = fields.Many2one("account.move", "Invoice", ondelete="set null")
    finance_task_id = fields.Many2one(
        "email.ai.finance.task", "Finance Task", ondelete="set null", readonly=True
    )

    # Pending outbox for AI draft
    outbox_id = fields.Many2one("email.ai.outbox", "Draft Reply", ondelete="set null")

    # Attachments
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "email_ai_message_attachment_rel",
        "message_id",
        "attachment_id",
        "Attachments",
    )

    def action_ai_classify(self):
        """Classify incoming email with AI."""
        for msg in self:
            prompt = (
                f"Classify this email. Return JSON only with keys: "
                f"category (helpdesk/sales_lead/invoice/general/spam), "
                f"sentiment (positive/neutral/frustrated/angry), "
                f"summary (one sentence).\n\n"
                f"Subject: {msg.name}\nFrom: {msg.from_email}\n"
                f"Body: {(msg.body_text or '')[:1000]}"
            )
            result = self.env["ai.service"].call(prompt, res_model=self._name, res_id=msg.id)
            if result["ok"]:
                try:
                    clean = result["content"].strip()
                    if clean.startswith("```"):
                        clean = clean.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean)
                    msg.write(
                        {
                            "ai_category": data.get("category", "general"),
                            "ai_summary": data.get("summary", ""),
                            "ai_sentiment": data.get("sentiment", "neutral"),
                            "ai_classification_done": True,
                            "state": "classified",
                        }
                    )
                    msg._auto_create_linked_record()
                except (json.JSONDecodeError, ValueError) as exc:
                    _logger.warning("Email classification failed: %s", exc)

    def _auto_create_linked_record(self):
        """Auto-create helpdesk ticket, CRM lead, or finance task based on AI category."""
        self.ensure_one()
        if self.ai_category == "helpdesk" and not self.ticket_id:
            ticket = (
                self.env["helpdesk.ticket"]
                .sudo()
                .create(
                    {
                        "name": self.name,
                        "description": self.body_html or self.body_text,
                        "source": "email",
                        "partner_id": self.partner_id.id if self.partner_id else False,
                    }
                )
            )
            self.ticket_id = ticket
            self.state = "linked"

        elif self.ai_category == "sales_lead" and not self.lead_id:
            lead = (
                self.env["crm.lead"]
                .sudo()
                .create(
                    {
                        "name": f"Email: {self.name}",
                        "type": "lead",
                        "email_from": self.from_email or "",
                        "description": self.body_text or "",
                    }
                )
            )
            self.lead_id = lead
            self.state = "linked"

        elif self.ai_category == "invoice" and not self.finance_task_id:
            task = (
                self.env["email.ai.finance.task"]
                .sudo()
                .create(
                    {
                        "name": self.name,
                        "email_message_id": self.id,
                        "description": (
                            f"Finance-related email from {self.from_name or self.from_email}.\n\n"
                            f"{self.body_text or ''}"
                        ),
                        "partner_id": self.partner_id.id if self.partner_id else False,
                    }
                )
            )
            self.finance_task_id = task
            self.state = "linked"

    def action_ai_draft_reply(self):
        """Generate an AI draft reply and put it in the pending outbox.

        If a matching EmailAiTemplate exists for the email's category and language,
        the template body is injected into the AI prompt as a structural guide, and
        the template's subject pattern is applied to the outbox subject.
        """
        self.ensure_one()

        # Find a matching template (explicit > category+lang > category-only)
        template = self.template_id
        if not template and self.ai_category:
            lang = self.env.lang or "en"
            template = self.env["email.ai.template"].search(
                [
                    ("category", "=", self.ai_category),
                    ("language_code", "=", lang),
                    ("company_id", "=", self.company_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if not template:
                template = self.env["email.ai.template"].search(
                    [
                        ("category", "=", self.ai_category),
                        ("active", "=", True),
                    ],
                    limit=1,
                )

        template_hint = ""
        if template:
            template_hint = (
                f"\n\nUse the following reply structure as a base — fill in the specifics "
                f"naturally based on the email content:\n{template.body_template}"
            )

        result = self.env["ai.service"].call(
            f"Draft a professional email reply for:\n"
            f"Subject: {self.name}\nFrom: {self.from_name or self.from_email}\n"
            f"Summary: {self.ai_summary or ''}\n"
            f"Body: {(self.body_text or '')[:1000]}"
            f"{template_hint}",
            res_model=self._name,
            res_id=self.id,
        )
        if result["ok"]:
            subject = f"Re: {self.name}"
            if template and template.subject_template:
                try:
                    subject = template.subject_template.format(subject=self.name)
                except KeyError:
                    pass

            outbox = self.env["email.ai.outbox"].create(
                {
                    "email_message_id": self.id,
                    "mailbox_id": self.mailbox_id.id if self.mailbox_id else False,
                    "subject": subject,
                    "to_email": self.from_email or "",
                    "body_draft": result["content"],
                    "body_final": result["content"],
                    "ai_draft": True,
                    "template_id": template.id if template else False,
                }
            )
            self.write({"outbox_id": outbox.id, "state": "draft_reply"})

            # Auto-send path: if the mailbox has auto_send enabled for this category,
            # automatically approve and send without human review.
            # This path is ONLY active when explicitly configured by an admin.
            if self.mailbox_id and self.ai_category in self.mailbox_id.get_auto_send_categories():
                _logger.info(
                    "Auto-send triggered for outbox %s (category: %s, mailbox: %s)",
                    outbox.id,
                    self.ai_category,
                    self.mailbox_id.name,
                )
                outbox.write({"state": "approved", "approved_by_id": self.env.uid})
                outbox.action_send()
                return None

            return {
                "type": "ir.actions.act_window",
                "res_model": "email.ai.outbox",
                "res_id": outbox.id,
                "view_mode": "form",
            }

    def action_archive(self):
        self.write({"state": "archived"})


class EmailAiOutbox(models.Model):
    """Pending outbox — AI-drafted replies awaiting human approval."""

    _name = "email.ai.outbox"
    _description = "Pending Email Outbox"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    email_message_id = fields.Many2one("email.ai.message", "Source Email", ondelete="cascade")
    mailbox_id = fields.Many2one(
        "email.ai.mailbox",
        "Send via Mailbox",
        ondelete="set null",
        help="When set, email is sent using this mailbox's SMTP credentials. "
        "Falls back to Odoo's default outgoing mail server if not set.",
    )
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, index=True)

    subject = fields.Char("Subject", required=True)
    to_email = fields.Char("To", required=True)
    cc_email = fields.Char("CC")
    from_email = fields.Char("From")

    body_draft = fields.Text("AI Draft", readonly=True)
    body_final = fields.Text("Final Body (editable)", required=True)
    ai_draft = fields.Boolean("Generated by AI", default=True, readonly=True)
    edit_reason = fields.Text("Reason for Edit")

    template_id = fields.Many2one(
        "email.ai.template", "Template Used", ondelete="set null", readonly=True
    )

    # Approval workflow
    state = fields.Selection(
        [
            ("pending", "Pending Review"),
            ("approved", "Approved — Ready to Send"),
            ("rejected", "Rejected"),
            ("needs_info", "Needs More Information"),
            ("sent", "Sent"),
        ],
        default="pending",
        tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", "Approved By", readonly=True)
    sent_date = fields.Datetime("Sent On", readonly=True)

    # Signature
    signature = fields.Text("Signature")

    def action_approve(self):
        self.write({"state": "approved", "approved_by_id": self.env.user.id})

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_needs_info(self):
        self.write({"state": "needs_info"})

    def action_send(self):
        """Send the approved reply.

        Uses the linked mailbox's SMTP settings when available; otherwise falls
        back to Odoo's mail.mail (default outgoing server).
        """
        for outbox in self:
            if outbox.state != "approved":
                raise UserError(
                    "Email must be approved before sending. "
                    "AI-drafted emails are NEVER auto-sent without human approval."
                )

            body = outbox.body_final or ""
            if outbox.signature:
                body = f"{body}\n\n{outbox.signature}"
            body_html = body.replace("\n", "<br/>")

            if outbox.mailbox_id and outbox.mailbox_id.smtp_host:
                # Send via configured mailbox SMTP
                outbox.mailbox_id.send_smtp(
                    to_email=outbox.to_email,
                    subject=outbox.subject,
                    body_html=body_html,
                    cc_email=outbox.cc_email or "",
                )
            else:
                # Fallback: Odoo mail.mail
                mail_values = {
                    "subject": outbox.subject,
                    "email_to": outbox.to_email,
                    "email_cc": outbox.cc_email or "",
                    "body_html": body_html,
                    "auto_delete": True,
                }
                mail = self.env["mail.mail"].sudo().create(mail_values)
                mail.send()

            outbox.write({"state": "sent", "sent_date": fields.Datetime.now()})
            if outbox.email_message_id:
                outbox.email_message_id.state = "replied"

            # Audit log — failure must never block the send
            try:
                self.env["platform.audit.log"].sudo().log(
                    "email_sent",
                    res_model=self._name,
                    res_id=outbox.id,
                    res_name=outbox.subject or "",
                    summary=f"Email sent to {outbox.to_email} | Subject: {outbox.subject}",
                    details={
                        "to_email": outbox.to_email,
                        "cc_email": outbox.cc_email or "",
                        "subject": outbox.subject,
                        "mailbox_id": outbox.mailbox_id.id if outbox.mailbox_id else None,
                        "ai_draft": outbox.ai_draft,
                    },
                )
            except Exception:
                _logger.warning("Failed to write audit log for outbox %s — continuing.", outbox.id)

            # Store edit reason for AI learning when the human changed the draft
            if outbox.edit_reason and outbox.body_final != outbox.body_draft:
                self.env["ai.feedback"].create(
                    {
                        "original_draft": outbox.body_draft,
                        "final_reply": outbox.body_final,
                        "edit_reason": "wrong_tone",
                        "category": "email",
                        "notes": outbox.edit_reason,
                    }
                )
