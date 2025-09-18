from odoo import models, fields,api
from odoo.exceptions import UserError
import requests




XERO_CONNECTIONS_URL = 'https://api.xero.com/connections'


XERO_API_URL = 'https://api.xero.com/'




class ResConfigSettings(models.Model):
    _name = 'res.config.settings.custom'
    _inherit = ['mail.thread'] 
    _description = 'Settings'


    # Master switch to activate the module's features
    xero_active = fields.Boolean(
        string="Enable Xero Synchronization",
        config_parameter='xero_integration.xero_active'
    )

    # API Credentials (from before)
    xero_client_id = fields.Char(
        string='Xero Client ID',
        config_parameter='xero_integration.client_id'
    )
    xero_client_secret = fields.Char(
        string='Xero Client Secret',
        config_parameter='xero_integration.client_secret'
    )
    xero_tenant_name = fields.Char(string="Xero Tenant Name", readonly=True, config_parameter='xero_integration.tenant_name')
    xero_tenant_id = fields.Char(string="Xero Tenant ID", readonly=True, config_parameter='xero_integration.tenant_id')



    # New Synchronization Rules
    xero_auto_sync_invoice = fields.Boolean(
        string="Auto-Sync Invoices on Posting",
        config_parameter='xero_integration.xero_auto_sync_invoice',
        help="If checked, invoices will be sent to Xero automatically when they are posted in Odoo."
    )
    xero_default_sales_account_id = fields.Many2one(
        'account.account',
        string='Default Sales Account',
        config_parameter='xero_integration.xero_default_sales_account_id',
        help="The default income account to be used for invoice lines in Xero."
    )



    xero_default_sales_account_code = fields.Char(
        string='Default Sales Account Code',
        config_parameter='xero_integration.default_sales_account_code',
        help="The default account code from your Xero Chart of Accounts to use for sales invoice lines (e.g., '200')."
    )





    def execute(self):
        """
        Called when the user clicks 'Apply'. This saves the permanent record
        and also saves the values to the central ir.config_parameter.
        """

        # import pdb; pdb.set_trace()
        self.ensure_one()
        # Save to ir.config_parameter
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('xero_integration.xero_active', self.xero_active)
        params.set_param('xero_integration.client_id', self.xero_client_id)
        params.set_param('xero_integration.client_secret', self.xero_client_secret)
        params.set_param('xero_integration.xero_auto_sync_invoice', self.xero_auto_sync_invoice)
        params.set_param('xero_integration.xero_default_sales_account_id', self.xero_default_sales_account_id.id)
        # We don't need to save tenant_id and tenant_name here because the config_parameter on the field does it automatically.

        # Re-open the settings view
        return {
            'type': 'ir.actions.act_window',
            'name': 'Settings',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }



    def button_connect_to_xero(self):
        """This method is called when the user clicks the 'Connect' button."""
        self.ensure_one()
        auth_url, error = self.env['xero.api.connector'].get_authorization_url()
        
        if not auth_url:
            raise UserError(error)
        else:
             self.execute()
        
       
        return {
            'type': 'ir.actions.act_url',
            'url': auth_url,
            'target': 'self',
        }
    



    def button_fetch_xero_tenants(self):
        """
        Fetches the connected tenants from Xero using the generic request method.
        """
        self.ensure_one()

        import pdb; pdb.set_trace()

        # Call the generic request method
        connections, error = self.env['xero.api.connector']._make_xero_request(
            endpoint='/connections',
            method='GET'
        )

        # Process the result
        if error:
            self.message_post(body=f"Error fetching tenants: {error}")
            return

        if not connections:
            self.message_post(body="No active Xero tenants found for this connection.")
            return

        first_tenant = connections[0]
        tenant_id = first_tenant.get('tenantId')
        tenant_name = first_tenant.get('tenantName')
        
        self.write({
            'xero_tenant_id': tenant_id,
            'xero_tenant_name': tenant_name,
        })

        self.execute()
        self.message_post(body=f"<b>Successfully connected to Xero Tenant:</b><br/><b>Name:</b> {tenant_name}<br/><b>ID:</b> {tenant_id}")
        
        # Re-open the settings view
        return {
            'type': 'ir.actions.act_window',
            'name': 'Settings',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }