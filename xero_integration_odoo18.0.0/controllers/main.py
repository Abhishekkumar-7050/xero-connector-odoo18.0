from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class XeroCallbackController(http.Controller):

    @http.route('/xero/callback', type='http', auth='user', website=True)
    def xero_callback(self, code=None, state=None, error=None, **kwargs):
        # import pdb;pdb.set_trace()
        """
        This controller handles the redirect from Xero.
        It performs all the actions for Step 2 of the docs.
        """
        # 1. Check for errors from Xero
        if error:
            _logger.error(f"Xero authorization failed with error: {error}")
            # Redirect to settings page with an error message
            return request.redirect('/web#action=xero_integration.xero_config_settings_action&error=true')

        # 2. Verify the 'state' parameter to prevent forgery attacks
        # In a real app, you would compare the received 'state' with one stored in the user's session.
        expected_state = "12345-abcdef" 
        if state != expected_state:
            _logger.warning("Xero callback state mismatch. Potential CSRF attack.")
            return request.redirect('/web#action=xero_integration.xero_config_settings_action&error=true')

        # 3. Exchange the temporary 'code' for a permanent 'access_token'
        # This calls the method we already wrote in our connector.
        success = request.env['xero.api.connector'].exchange_code_for_tokens(code)
        
        if success:
            # Redirect back to the settings page with a success flag
            _logger.info("Xero token exchange successful.")
            return request.redirect('/web#action=xero_integration.xero_config_settings_action&xero_auth=success')
        else:
            # Redirect back with an error flag if the exchange failed
            _logger.error("Failed to exchange Xero code for tokens.")
            return request.redirect('/web#action=xero_integration.xero_config_settings_action&error=true')