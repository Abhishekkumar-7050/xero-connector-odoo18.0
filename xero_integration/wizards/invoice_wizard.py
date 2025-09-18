from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class XeroInvoiceSyncWizard(models.TransientModel):
    _name = 'xero.invoice.sync.wizard'
    _description = 'Xero Invoice Import/Export Wizard'

    operation = fields.Selection([
        ('import', 'Import from Xero'),
        ('export', 'Export to Xero')
    ], string="Operation", required=True, default='import')

    def action_confirm_sync(self):
            """
            Executes the invoice sync and then shows a summary notification.
            """
            self.ensure_one()
            
            connector = self.env['xero.api.connector']
            object_name = "Invoices"
            results = {}

            try:
                if self.operation == 'import':
                    # 1. Call the sync function and capture the results
                    results = connector._import_xero_invoices()
                elif self.operation == 'export':
                    results = connector._export_odoo_invoices()
                
                # 2. On success, show the success notification
                return connector._show_sync_notification(object_name, results)

            except Exception as e:
                _logger.error(f"Failed to sync {object_name}: {e}", exc_info=True)
                # 3. On failure, show a failure notification
                error_message = str(e)
                return connector._show_sync_notification(object_name, results)