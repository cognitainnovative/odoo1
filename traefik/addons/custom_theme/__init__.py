from . import controllers, models


def post_init_hook(env):
    """Reorder platform menus into logical zones after install.

    Uses env.ref(..., raise_if_not_found=False) so this is a no-op for any
    menu whose module is not yet installed. Re-running the module update
    re-applies the sequences.
    """
    ZONE_MAP = [
        ("crm.crm_menu_root", 10),
        ("sale.sale_menu_root", 11),
        ("account.menu_finance", 20),
        ("hr.menu_hr_root", 30),
        ("custom_payroll_nl.menu_payroll_root", 31),
        ("stock.menu_stock_root", 40),
        ("custom_rental.menu_rental_root", 41),
        ("custom_planning.menu_planning_root", 42),
        ("purchase.menu_purchase_root", 43),
        ("custom_helpdesk.menu_helpdesk_root", 50),
        ("custom_ai_chatbot.menu_chatbot_root", 51),
        ("custom_whatsapp_social.menu_social_root", 52),
        ("custom_ai_voice.menu_voice_root", 53),
    ]
    for xmlid, seq in ZONE_MAP:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu:
            menu.sequence = seq
