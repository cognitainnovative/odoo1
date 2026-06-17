"""Route-level subscription gate.

Usage in other addon controllers:
    from odoo.addons.custom_subscription_modules.controllers.gate import require_module

    class MyController(http.Controller):
        @http.route('/my/route', auth='user')
        @require_module('crm')
        def my_handler(self, **kw):
            ...
"""

import functools
import logging

from odoo.http import request

_logger = logging.getLogger(__name__)


def require_module(module_code):
    """Decorator that returns 403 if the subscription for module_code is inactive."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            env = request.env
            Sub = env["platform.subscription"]
            if not Sub.is_module_active(module_code):
                _logger.warning(
                    "Route blocked: module '%s' not active for company %s",
                    module_code,
                    env.company.name,
                )
                return request.make_json_response(
                    {"error": "module_inactive", "module": module_code},
                    status=403,
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
