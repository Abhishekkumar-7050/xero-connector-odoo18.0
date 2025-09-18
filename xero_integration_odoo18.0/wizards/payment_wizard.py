from odoo import models, fields

class XeroPaymentSyncWizard(models.TransientModel):
    _name = 'xero.payment.sync.wizard'
    _description = 'Xero Payment Import/Export Wizard'

    operation = fields.Selection([
        ('import', 'Import Payments from Xero'),
        ('export', 'Export Payments to Xero')
    ], string="Operation", required=True, default='import')

    def action_confirm_sync(self):
            """
            Executes the payment sync and then shows a summary notification.
            """
            self.ensure_one()
            
            connector = self.env['xero.api.connector']
            object_name = "Payments"
            results = {}

            try:
                if self.operation == 'import':
                    # 1. Call the sync function and capture the results dictionary
                    results = connector._import_xero_payments()
                elif self.operation == 'export':
                    results = connector._export_odoo_payments()
                
                # 2. On success, show the success notification
                return connector._show_sync_notification(object_name, results)
            except Exception as e:
                 pass

            