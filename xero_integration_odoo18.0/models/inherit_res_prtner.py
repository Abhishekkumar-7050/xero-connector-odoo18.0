from odoo import models, fields

class ResPartner(models.Model):
    """
    Inherits the res.partner model to add a field to store the Xero Contact ID.
    """
    _inherit = 'res.partner'

    xero_contact_id = fields.Char(
        string='Xero Contact ID',
        readonly=True,
        copy=False,
        help="The unique identifier for this contact in Xero."
    )