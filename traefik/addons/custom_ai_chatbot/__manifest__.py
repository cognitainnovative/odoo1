{
    "name": "Platform AI Chatbot",
    "version": "19.0.1.0.0",
    "summary": "Website chat widget, RAG answers, lead capture, escalation, employee support app.",
    "author": "Cognita Innovative",
    "license": "LGPL-3",
    "category": "Website",
    "depends": ["website", "crm", "mail", "custom_ai_core", "custom_platform_security"],
    "data": [
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "data/chatbot_config.xml",
        "views/chat_config_views.xml",
        "views/chat_transcript_views.xml",
        "views/website_templates.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "custom_ai_chatbot/static/src/js/chat_widget.js",
            "custom_ai_chatbot/static/src/scss/chat_widget.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
