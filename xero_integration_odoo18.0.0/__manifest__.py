# __manifest__.py
{
    'name': "Xero Integration",
    # 'version': '1.0',
    'version':'17.0.1.0.0',
    'summary': "Integrate Odoo with Xero Accounting",
    'author': " Abhishek Kumar ",
    'web_icon': 'xero_integration_odoo18.0.0,static/src/img/icon.png',
    'license': 'OPL-1',
    'depends': ['base', 'account','mail'], 

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
    'images': [
    'static/description/icon.png',  # This will be your app icon
    ],

    'installable': True,
    'application': True,
}