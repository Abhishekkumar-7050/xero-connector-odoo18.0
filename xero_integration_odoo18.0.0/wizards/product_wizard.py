from odoo import models, fields

class XeroProductSyncWizard(models.TransientModel):
    _name = 'xero.product.sync.wizard'
    _description = 'Xero Product/Item Import/Export Wizard'

    operation = fields.Selection([
        ('import', 'Import Products/Items from Xero'),
        ('export', 'Export Products/Items to Xero')
    ], string="Operation", required=True, default='import')

    def action_confirm_sync(self):
        """
        Executes the product import or export operation.
        """
        self.ensure_one()
        results = {}
        object_name = "Products"

        
        connector = self.env['xero.api.connector']

        if self.operation == 'import':
            # Calls the item import function we created
           results = connector._import_xero_items()
        elif self.operation == 'export':
            # Calls the item export function we created
           results = connector._export_odoo_products()

        return connector._show_sync_notification(object_name, results)