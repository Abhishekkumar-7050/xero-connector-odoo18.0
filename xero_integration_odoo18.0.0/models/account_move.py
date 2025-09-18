# models/account_move.py
from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    xero_invoice_id = fields.Char(
        string='Xero Invoice ID',
        copy=False,
        readonly=True,
        index=True
    )

   
class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    xero_lineitem_id = fields.Char(
        string='Xero LineItem ID',
        copy=False,
        readonly=True
    )


class AccountAccount(models.Model):
    _inherit = 'account.account'

    xero_account_id = fields.Char(
        string='Xero Account ID',
        copy=False,
        readonly=True,
        index=True
    )

class ProductProduct(models.Model):
    _inherit = 'product.product'

    xero_item_id = fields.Char(
        string='Xero Item ID',
        copy=False,
        readonly=True,
        index=True
    )


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    xero_payment_id = fields.Char(
        string='Xero Payment ID',
        copy=False,
        readonly=True,
        index=True
    )