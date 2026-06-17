{
    "name": "Platform Security & Compliance",
    "version": "19.0.1.0.0",
    "summary": (
        "RBAC groups, central immutable audit log, GDPR data management, "
        "scoped API tokens, data residency settings. Required by all platform addons."
    ),
    "author": "Cognita Innovative",
    "license": "LGPL-3",
    "category": "Technical",
    "depends": ["base", "mail", "web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "data/cron.xml",
        "views/audit_log_views.xml",
        "views/api_token_generate_views.xml",
        "views/api_token_views.xml",
        "views/gdpr_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "external_dependencies": {
        "python": ["cryptography"],
    },
}
