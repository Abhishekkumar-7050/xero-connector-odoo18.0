from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class XeroContactSyncWizard(models.TransientModel):
    _name = 'xero.contact.sync.wizard'
    _description = 'Xero Contact Import/Export Wizard'

    @api.model
    def _default_xero_tenant(self):
        latest_settings = self.env['res.config.settings.custom'].search([], order='id desc', limit=1)
        if latest_settings and latest_settings.xero_tenant_id:
            return latest_settings.xero_tenant_id.id
        return False

    operation = fields.Selection([
        ('export', 'Export All Odoo Contacts to Xero'),
        ('import', 'Import All Xero Contacts to Odoo')
    ], string="Operation", required=True, default='export')

   

    def action_confirm_sync(self):
        """
        Executes the contact sync and then shows a summary notification.
        """
        self.ensure_one()
        
        connector = self.env['xero.api.connector']
        results = {}
        object_name = "Contacts"

        # Call the correct sync function based on the user's choice
        if self.operation == 'import':
            # Capture the dictionary of stats that the function returns
            results = connector._import_all_xero_contacts()
        elif self.operation == 'export':
            results = connector._export_all_odoo_contacts()

        # Pass the stats to the notification helper and return its action
        # This is what triggers the popup in the user interface.
        return connector._show_sync_notification(object_name, results)