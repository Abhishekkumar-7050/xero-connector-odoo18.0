# __manifest__.py
{
    'name': "Xero Integration",
    'version': '1.0',
    'summary': "Integrate Odoo with Xero Accounting",
    'author': " Abhishek Kumar ",
    'depends': ['base', 'account','mail'], # 'account' zaroori hai
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/res_config_settings_view.xml',
        'views/invoice_export_wizard.xml',
        'views/account_move_view.xml',
        'views/contact_import_export_wizard.xml',
        'views/product_import_export_wizard.xml',
        'views/payments_import_export_wizard.xml',
    ],
    'installable': True,
    'application': True,
}