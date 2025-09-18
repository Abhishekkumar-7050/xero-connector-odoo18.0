import base64
import requests
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError
import urllib.parse

_logger = logging.getLogger(__name__)

XERO_AUTH_URL = 'https://login.xero.com/identity/connect/authorize'
XERO_TOKEN_URL = 'https://identity.xero.com/connect/token'
XERO_API_URL = 'https://api.xero.com/api.xro/2.0'


class XeroConnector(models.AbstractModel):
    _name = 'xero.api.connector'
    _description = 'Xero API Connector'



    def _make_xero_request(self, endpoint, method='GET', json_data=None):
        """
        A generic, reusable function to make any request to the Xero API.
        """
        # import pdb; pdb.set_trace()
        params = self.env['ir.config_parameter'].sudo()
        access_token = params.get_param('xero_integration.access_token')

        # print(" token " , access_token)

        tenant_id = params.get_param('xero_integration.tenant_id')

        # print("tanent id" , tenant_id)

        if not access_token :
            return False, "Xero is not fully connected. Please connect and fetch tenants from the settings."

       
        headers = {
            'Authorization': f"Bearer {access_token}",
            'Xero-Tenant-Id': tenant_id,
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        
        url = f"{XERO_API_URL}{endpoint}"

        try:
            # 3. Make the API call using the specified method
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=json_data, timeout=15)
            # You can add other methods like PUT, DELETE here if needed
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, json=json_data, timeout=50)
            else:
              return False, f"Unsupported HTTP method: {method}"

            response.raise_for_status()
            # 4. Handle the response
            if not response.ok:
            # <<< ADD THIS DEBUGGER LINE HERE >>>
                # import pdb; pdb.set_trace()
                
                error_msg = f"Xero API Error: {response.status_code} - {response.text}"
                _logger.error(f"Xero detailed error: {error_msg}")
                return False, error_msg
             # Handle a successful response
            return response.json(), None # Returns a tuple



            

        except requests.exceptions.RequestException as e:
            error_msg = f"Network error connecting to Xero: {e}"

            return False, error_msg


    def get_authorization_url(self):
        """
        Generates the URL to send the user to for authorization.
        It fetches settings from the latest 'res.config.settings.custom' record.
        """
       
        latest_settings = self.env['res.config.settings.custom'].search([], order='id desc', limit=1)
        if not latest_settings:
            return False, "No Xero settings have been saved yet. Please go to Configuration -> Settings and save your settings first."

        client_id = latest_settings.xero_client_id
        if not client_id:
            return False, "The Xero Client ID is not set in your saved settings. Please add it and save."

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        if not base_url:
            return False, "The 'web.base.url' system parameter is not set. Please configure it in Odoo's Technical Settings."

        redirect_uri = f"http://localhost:8015/xero/callback"
        scopes = [
                'openid', 
                'profile', 
                'email',
                
                # CRITICAL: Allows you to get a refresh token for long-term access
                'offline_access',
                
                # Accounting Scopes
                'accounting.transactions',  # Invoices, bills, payments, etc.
                'accounting.contacts',      # Customers and suppliers
                'accounting.journals.read', # General ledger entries
                'accounting.settings',      # Organisation settings, chart of accounts, tax rates
                'accounting.attachments',   # Attach files to transactions
                
                # Optional but common scopes
                'projects',                 # Xero Projects
                'payroll.employees',        # Payroll in AU, NZ, UK
                'payroll.payruns',
                'payroll.settings'
            ]

        # Join the list into a single, space-delimited string
        scope_string = ' '.join(scopes)

        state = "12345-abcdef" 

        auth_params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': scope_string,
            'state': state,
        }
        
        auth_url = f"{XERO_AUTH_URL}?" + urllib.parse.urlencode(auth_params)

        return auth_url, ""

#======================Cron jobs  running automattically in a day =============
    @api.model
    def run_daily_sync(self):
        """
        This method is designed to be called by a scheduled action (cron job).
        It only runs if the auto-sync setting is enabled.
        """
        params = self.env['ir.config_parameter'].sudo()
        auto_sync_enabled = params.get_param('xero_integration.xero_auto_sync_invoice')

        if not auto_sync_enabled:
            _logger.info("Xero daily sync is disabled in the settings. Skipping.")
            return True


        _logger.info("--- Starting Daily Xero Sync Cron Job (Enabled) ---")
        
        # --- IMPORT FROM XERO TO ODOO ---
        _logger.info("Step 1: Importing from Xero...")
        self._import_xero_accounts()
        self._import_all_xero_contacts()
        self._import_xero_items()
        self._import_xero_invoices()
        self._import_xero_payments()
        
        # --- EXPORT FROM ODOO TO XERO ---
        _logger.info("Step 2: Exporting from Odoo...")
        self._export_odoo_accounts()
        self._export_all_odoo_contacts()
        self._export_odoo_products()
        self._export_odoo_invoices()
        self._export_odoo_payments()
        
        _logger.info("--- Daily Xero Sync Cron Job Finished ---")
        return True  
  
#=================================refresh token by cron =============================== 
    @api.model
    def _refresh_xero_token(self):
        """
        Refreshes the Xero access token using the stored refresh token.
        This method is designed to be called by a cron job.
        """
        _logger.info("Attempting to refresh Xero access token...")
        params = self.env['ir.config_parameter'].sudo()
        refresh_token = params.get_param('xero_integration.refresh_token')

        # Find the latest saved settings to get client_id and client_secret
        latest_settings = self.env['res.config.settings.custom'].search([], order='id desc', limit=1)
        if not latest_settings or not refresh_token:
            _logger.error("Xero refresh failed: Missing refresh token or client settings.")
            return False

        client_id = latest_settings.xero_client_id
        client_secret = latest_settings.xero_client_secret

        # 1. Prepare the request headers and body as per Xero's docs
        auth_header = base64.b64encode(
            (f"{client_id}:{client_secret}").encode("utf-8")
        ).decode("utf-8")
        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        body = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }

        try:
            # 2. Make the API call to the token endpoint
            response = requests.post(XERO_TOKEN_URL, headers=headers, data=body, timeout=15)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

            # 3. If successful, save the new tokens
            data = response.json()
            new_access_token = data['access_token']
            new_refresh_token = data['refresh_token']
            
            params.set_param('xero_integration.access_token', new_access_token)
            params.set_param('xero_integration.refresh_token', new_refresh_token)
            
            _logger.info("Successfully refreshed and saved new Xero tokens.")
            return True

        except requests.exceptions.RequestException as e:
            error_text = e.response.text if e.response else str(e)
            _logger.error(f"Error refreshing Xero token: {error_text}")
            return False




    # not in used 
    def exchange_code_for_tokens(self, auth_code):
        """Exchanges the authorization code for tokens and saves the tenant ID."""
        
        latest_settings = self.env['res.config.settings.custom'].search([], order='id desc', limit=1)
        if not latest_settings or not latest_settings.xero_client_id or not latest_settings.xero_client_secret:
            _logger.error("Xero settings (Client ID/Secret) are not configured.")
            return False

        client_id = latest_settings.xero_client_id
        client_secret = latest_settings.xero_client_secret
        
        auth_header = base64.b64encode(
            (f"{client_id}:{client_secret}").encode("utf-8")
        ).decode("utf-8")

        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        # <<< CHANGE: Use the dynamic base_url for consistency >>>
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        redirect_uri = f"{base_url}/xero/callback"

        body = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': redirect_uri,
        }

        try:
            # import pdb; pdb.set_trace()
            # Step 1: Exchange code for tokens
            response = requests.post(XERO_TOKEN_URL, headers=headers, data=body, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            access_token = token_data['access_token']
            refresh_token = token_data['refresh_token']
            
            # Step 2: Save the new tokens
            params = self.env['ir.config_parameter'].sudo()
            params.set_param('xero_integration.access_token', access_token)
            # <<< FIX: Uncommented this line to save the refresh token >>>
            params.set_param('xero_integration.refresh_token', refresh_token)
            _logger.info("Successfully fetched and saved Xero tokens.")
            
            # <<< ADDED START: This is the critical missing step >>>
            # Step 3: Use the new access token to get the Tenant ID
            connections_headers = {
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            }
            connections_response = requests.get('https://api.xero.com/connections', headers=connections_headers, timeout=10)
            connections_response.raise_for_status()
            connections_data = connections_response.json()
            
            if connections_data and len(connections_data) > 0:
                tenant_id = connections_data[0]['tenantId']
                params.set_param('xero_integration.tenant_id', tenant_id)
                _logger.info(f"Successfully fetched and saved Xero Tenant ID: {tenant_id}")
            else:
                _logger.error("Could not find any tenants (connections) for this user.")
                return False
            # <<< ADDED END >>>

            return True
    
        except requests.exceptions.RequestException as e:
            error_text = e.response.text if e.response else str(e)
            _logger.error(f"Error during Xero token exchange or connection fetch: {error_text}")
            return False

    #========================== cantacts =====================================
    def _export_all_odoo_contacts(self):
        """
        Finds all Odoo partners without a xero_contact_id and syncs them to Xero.
        NOW RETURNS A DICTIONARY OF RESULTS.
        """
        _logger.info("Starting bulk export of Odoo contacts to Xero.")
        
        partners_to_sync = self.env['res.partner'].search([('xero_contact_id', '=', False)])
        _logger.info(f"Found {len(partners_to_sync)} contacts to export.")
        
        # Rename for consistency with the return dictionary
        created_count = 0
        error_count = 0
        
        for partner in partners_to_sync:
            try:
                self._get_or_create_xero_contact(partner)
                created_count += 1
                
                if created_count % 10 == 0:
                    self.env.cr.commit()
            except Exception as e:
                _logger.error(f"Failed to sync contact '{partner.name}': {e}")
                error_count += 1
        
        self.env.cr.commit()
        _logger.info(f"Bulk contact sync complete. Synced: {created_count}, Errors: {error_count}")
        
        # <<< CHANGE: Return a dictionary with the results for the notification system >>>
        # Since this function only exports contacts that have never been synced,
        # we count them all as 'created'.
        return {'created': created_count, 'updated': 0}

    def _get_or_create_xero_contact(self, odoo_partner):

        """
        Finds a contact in Xero by name, or creates/updates it with more detail.
        Returns the Xero ContactID.
        """
        # import pdb;pdb.set_trace()
        # 1. Prepare a detailed data payload from the Odoo partner record
        contact_data = {
            'Name': odoo_partner.name,
            'EmailAddress': odoo_partner.email or '',
            'Phones': [
                {'PhoneType': 'DEFAULT', 'PhoneNumber': odoo_partner.phone or ''},
                {'PhoneType': 'MOBILE', 'PhoneNumber': odoo_partner.mobile or ''}
            ],
            'Addresses': [
                {
                    'AddressType': 'STREET',
                    'AddressLine1': odoo_partner.street or '',
                    'AddressLine2': odoo_partner.street2 or '',
                    'City': odoo_partner.city or '',
                    'PostalCode': odoo_partner.zip or '',
                    'Country': odoo_partner.country_id.name or ''
                }
            ],
            'Website': odoo_partner.website or ''
        }
        
        # 2. If we have a saved ID, perform an UPDATE.
        if odoo_partner.xero_contact_id:
            contact_data['ContactID'] = odoo_partner.xero_contact_id
            response_data, error = self._make_xero_request(
                '/Contacts', 'POST', json_data={'Contacts': [contact_data]}
            )
            if error:
                raise UserError(f"Could not update contact {odoo_partner.name} in Xero. Error: {error}")
            return odoo_partner.xero_contact_id

        # 3. If no saved ID, SEARCH for the contact in Xero by exact name.
        contact_name_encoded = urllib.parse.quote(f'"{odoo_partner.name}"')
        endpoint = f'/Contacts?where=Name=={contact_name_encoded}'
        response_data, error = self._make_xero_request(endpoint)

        if error:
            raise UserError(f"Could not search for contact in Xero. Error: {error}")

        if response_data.get('Contacts'):
            # Contact was found
            xero_contact_id = response_data['Contacts'][0]['ContactID']
        else:
            # Contact not found, so CREATE it.
            response_data, error = self._make_xero_request(
                '/Contacts', 'POST', json_data={'Contacts': [contact_data]}
            )
            if error:
                raise UserError(f"Could not create contact in Xero. Error: {error}")
            xero_contact_id = response_data['Contacts'][0]['ContactID']

        # 4. Save the new ID back to the Odoo partner and return it.
        odoo_partner.write({'xero_contact_id': xero_contact_id})
        return xero_contact_id
    

    def _import_all_xero_contacts(self):
        """
        Fetches all contacts from Xero and creates them in Odoo if they don't exist.
        NOW RETURNS A DICTIONARY OF RESULTS.
        """
        _logger.info("Starting bulk import of Xero contacts to Odoo.")
        
        response_data, error = self._make_xero_request('/Contacts')

        if error:
            _logger.error(f"Failed to fetch contacts from Xero: {error}")
            # Return stats even on failure
            return {'created': 0, 'updated': 0}

        partner_model = self.env['res.partner']
        # Rename for consistency
        created_count = 0
        
        for contact_data in response_data.get('Contacts', []):
            xero_contact_id = contact_data.get('ContactID')
            
            existing_partner = partner_model.search([('xero_contact_id', '=', xero_contact_id)], limit=1)
            if existing_partner:
                continue # This function only creates, it does not update

            # Create the new Odoo partner
            partner_model.create({
                'name': contact_data.get('Name'),
                'email': contact_data.get('EmailAddress'),
                'phone': contact_data.get('Phones', [{}])[0].get('PhoneNumber'),
                'xero_contact_id': xero_contact_id,
            })
            created_count += 1
        
        _logger.info(f"Bulk contact import complete. Created: {created_count} new contacts.")
        
        # <<< CHANGE: Return a dictionary with the results for the notification system >>>
        # Since this function only creates, updated is always 0.
        return {'created': created_count, 'updated': 0}
    


    #========================= account mapping ==========================
    def _import_xero_accounts(self):
        """
        Fetches all accounts from Xero and creates or updates them in Odoo.
        If an account is a bank account, it also creates or updates the corresponding Bank Journal.
        """
        _logger.info("Starting sync of Xero Chart of Accounts to Odoo.")

        # import pdb; pdb.set_trace()
        
        response_data, error = self._make_xero_request('/Accounts')
        if error:
            _logger.error(f"Failed to fetch accounts from Xero: {error}")
            return False

        account_model = self.env['account.account']
        journal_model = self.env['account.journal']
        created_count = 0
        updated_count = 0
        
        current_company_id = self.env.company.id

        for xero_account in response_data.get('Accounts', []):
            account_code = xero_account.get('Code')
            xero_account_id = xero_account.get('AccountID')
            if not account_code or not xero_account_id:
                continue
                
            # Search for an existing account by Xero ID, then by code for the current company
            search_domain = [('code', '=', account_code), ('company_ids', 'in', current_company_id)]
            
            existing_account = account_model.search([('xero_account_id', '=', xero_account_id)], limit=1)
            if not existing_account:
                existing_account = account_model.search(search_domain, limit=1)

            type_mapping = {
                'BANK': 'asset_cash', 'CURRLIAB': 'liability_current',
                'DEPRECIATN': 'asset_non_current', 'DIRECTCOSTS': 'expense',
                'EQUITY': 'equity', 'EXPENSE': 'expense', 'FIXED': 'asset_non_current',
                'LIABILITY': 'liability_current', 'REVENUE': 'income', 'SALES': 'income',
            }
            odoo_account_type = type_mapping.get(xero_account.get('Type'), 'asset_current')

            vals = {
                'name': xero_account.get('Name'),
                'code': account_code,
                'account_type': odoo_account_type,
                'xero_account_id': xero_account_id,
                'company_ids': [(6, 0, [current_company_id])],
            }

            odoo_account = None
            if existing_account:
                existing_account.write(vals)
                odoo_account = existing_account
                updated_count += 1
            else:
                odoo_account = account_model.create(vals)
                created_count += 1
            
            # <<< COMPLETED LOGIC START: Create or Update the corresponding Journal >>>
            # import pdb; pdb.set_trace()
            # if xero_account.get('Type') == 'BANK':
                # Check if a journal for this bank account already exists
            existing_journal = journal_model.search([('default_account_id', '=', odoo_account.id)], limit=1)
                
            if not existing_journal:
                    _logger.info(f"Creating new Bank Journal for account '{odoo_account.name}'")
                    journal_model.create({
                        'name': odoo_account.name,
                        'type': 'bank',
                        'code': odoo_account.code[:5], # Use first 5 chars for a short code
                        'default_account_id': odoo_account.id,
                        'company_id': current_company_id,
                    })
            else:
                    # If the journal exists, update it to match the account name/code
                    _logger.info(f"Updating existing Bank Journal for account '{odoo_account.name}'")
                    existing_journal.write({
                        'name': odoo_account.name,
                        'code': odoo_account.code[:5],
                    })
            # <<< COMPLETED LOGIC END >>>
        
        _logger.info(f"Chart of Accounts sync complete. Created: {created_count}, Updated: {updated_count}.")
        return True
    

    def _export_odoo_accounts(self):
        """
        Finds all Odoo accounts without a xero_account_id and creates them in Xero.
        """
        accounts_to_sync = self.env['account.account'].search([('xero_account_id', '=', False)])
        _logger.info(f"Found {len(accounts_to_sync)} Odoo accounts to export.")
        
        synced_count = 0
        
        for odoo_account in accounts_to_sync:
            # <<< FIX 1: More complete mapping dictionary >>>
            # This covers most of the standard Odoo account types.
            reverse_type_mapping = {
                'asset_receivable': 'ACCREC',
                'asset_cash': 'BANK',
                'asset_current': 'CURRENT',
                'asset_non_current': 'FIXED',
                'asset_prepayment': 'PREPAYMENT',
                'liability_payable': 'ACCPAY',
                'liability_credit_card': 'CREDITCARD',
                'liability_current': 'CURRLIAB',
                'liability_non_current': 'TERMLIAB',
                'equity': 'EQUITY',
                'equity_unallocated': 'EQUITY',
                'income': 'REVENUE',
                'income_other': 'OTHERINCOME',
                'expense': 'EXPENSE',
            }
            xero_type = reverse_type_mapping.get(odoo_account.account_type)
            
            # <<< FIX 2: Uncommented the essential safety check >>>
            # This will safely skip any account whose type cannot be mapped.
            if not xero_type:
                _logger.warning(
                    f"Skipping account {odoo_account.code} - cannot map Odoo type "
                    f"'{odoo_account.account_type}' to a Xero type."
                )
                continue

            payload = {
                'Code': odoo_account.code,
                'Name': odoo_account.name,
                'Type': xero_type,
                'Description': odoo_account.note or '',
            }
            
            # Note: Xero docs use PUT for creating single accounts. POST is for bulk.
            response_data, error = self._make_xero_request('/Accounts', method='PUT', json_data=payload)
            
            if error:
                _logger.error(f"Failed to export account {odoo_account.code}. Error: {error}")
                continue

            if response_data.get('Accounts'):
                new_xero_id = response_data['Accounts'][0]['AccountID']
                odoo_account.write({'xero_account_id': new_xero_id})
                synced_count += 1
                
        _logger.info(f"Account export complete. Synced: {synced_count} new accounts.")
        return True
    
   




    #===================== Invoices ( while importing the  invoice  creating the account in odoo if acount does not exists) ======================================

    def _import_xero_invoices(self):
        """
        Fetches all invoices from Xero and creates them in Odoo if they don't exist.
        NOW RETURNS A DICTIONARY OF RESULTS.
        """
        _logger.info("Starting bulk import of Xero invoices to Odoo.")
        
        response_data, error = self._make_xero_request('/Invoices')
        if error:
            _logger.error(f"Failed to fetch invoice list from Xero: {error}")
            return {'created': 0, 'updated': 0}

        invoices_in_xero = response_data.get('Invoices', [])
        _logger.info(f"Found {len(invoices_in_xero)} invoices in Xero.")
        
        invoice_model = self.env['account.move']
        created_count = 0
    
        for invoice_summary in invoices_in_xero:
            xero_invoice_id = invoice_summary.get('InvoiceID')
            existing_invoice = invoice_model.search([('xero_invoice_id', '=', xero_invoice_id)], limit=1)
            if existing_invoice:
                continue # This function only creates, it does not update
            
            full_invoice_data, error = self._make_xero_request(f'/Invoices/{xero_invoice_id}')
            if error or not full_invoice_data.get('Invoices'):
                _logger.error(f"Could not fetch details for Xero Invoice {xero_invoice_id}: {error}")
                continue

            invoice_detail = full_invoice_data['Invoices'][0]
            self._create_odoo_invoice_from_xero_data(invoice_detail)
            created_count += 1
            
            if created_count % 10 == 0:
                self.env.cr.commit()

        self.env.cr.commit()
        _logger.info(f"Bulk invoice import complete. Imported: {created_count} new invoices.")
        
        # <<< CHANGE: Return a dictionary with the results for the notification system >>>
        return {'created': created_count, 'updated': 0}
    


    def _create_odoo_invoice_from_xero_data(self, xero_invoice_data):
        """
        Creates a single Odoo account.move record from detailed Xero invoice JSON.

        """
        # import pdb;pdb.set_trace()
        # 1. Find the corresponding Odoo Partner (Customer/Vendor)
        xero_contact_id = xero_invoice_data.get('Contact', {}).get('ContactID')
        partner = self.env['res.partner'].search([('xero_contact_id', '=', xero_contact_id)], limit=1)
        if not partner:
            _logger.warning(f"Skipping invoice {xero_invoice_data.get('InvoiceNumber')} - Partner with Xero ID {xero_contact_id} not found.")
            return

        # 2. Determine Invoice Type (Customer Invoice vs. Vendor Bill)
        move_type = ''
        if xero_invoice_data.get('Type') == 'ACCREC': # Accounts Receivable
            move_type = 'out_invoice'
        elif xero_invoice_data.get('Type') == 'ACCPAY': # Accounts Payable
            move_type = 'in_invoice'
        else:
            _logger.warning(f"Skipping invoice with unknown type: {xero_invoice_data.get('Type')}")
            return

        invoice_date_str = xero_invoice_data.get('DateString', '').split('T')[0]
        due_date_str = xero_invoice_data.get('DueDateString', '').split('T')[0]

        invoice_vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': invoice_date_str if invoice_date_str else None,
            'invoice_date_due': due_date_str if due_date_str else None,
            'xero_invoice_id': xero_invoice_data.get('InvoiceID'),
            'ref': xero_invoice_data.get('Reference') if move_type == 'in_invoice' else '',
        }

        # 4. Prepare Invoice Lines
        invoice_line_ids = []
        for line in xero_invoice_data.get('LineItems', []):
            # This is a simplified example. You need a robust way to find the correct
            # account and taxes based on your Odoo setup.
            accountcode = line.get('AccountCode')
            account = self.env['account.account'].search([('code', '=', accountcode )], limit=1)
            if not account:
                # _logger.warning(f"Account with code {line.get('AccountCode')} not found. Skipping line.")
                self._import_xero_accounts()  # account
                account = self.env['account.account'].search([('code', '=', accountcode)], limit=1)
            
                
                invoice_line_ids.append((0, 0, {
                    'name': line.get('Description'),
                    'quantity': line.get('Quantity', 1),
                    'price_unit': line.get('UnitAmount', 0.0),
                    'account_id': account.id or 200,
                    'xero_lineitem_id': line.get('LineItemID'),
                    # Tax mapping is complex and specific to your setup.
                    # 'tax_ids': [(6, 0, [tax_id_1, tax_id_2])], 
                }))
            else:
                
                  invoice_line_ids.append((0, 0, {
                    'name': line.get('Description'),
                    'quantity': line.get('Quantity', 1),
                    'price_unit': line.get('UnitAmount', 0.0),
                    'account_id': account.id or 200,
                    'xero_lineitem_id': line.get('LineItemID'),
                    # Tax mapping is complex and specific to your setup.
                    # 'tax_ids': [(6, 0, [tax_id_1, tax_id_2])], 
                }))
        
        invoice_vals['invoice_line_ids'] = invoice_line_ids
        
        # 5. Create the invoice
        new_invoice = self.env['account.move'].create(invoice_vals)
        
        # You might want to handle the invoice state based on Xero's 'Status' field
        if xero_invoice_data.get('Status') in ['AUTHORISED', 'PAID']:
            new_invoice.action_post()
            
        _logger.info(f"Successfully created invoice {new_invoice.name} from Xero Invoice {xero_invoice_data.get('InvoiceNumber')}.")
        return new_invoice
    


    def _update_odoo_invoice_from_xero_data(self, odoo_invoice, xero_invoice_data):
        """
        Updates an existing Odoo invoice with data from the Xero invoice JSON.
        """
        if odoo_invoice.state != 'draft':
            _logger.info(f"Skipping update for invoice {odoo_invoice.name} because it is not in draft state.")
            return


        odoo_invoice.invoice_line_ids.unlink()
        invoice_line_ids = []
        for line in xero_invoice_data.get('LineItems', []):
            account = self.env['account.account'].search([('code', '=', line.get('AccountCode'))], limit=1)
            if not account:
                continue
                
            invoice_line_ids.append((0, 0, {
                'name': line.get('Description'),
                'quantity': line.get('Quantity', 1),
                'price_unit': line.get('UnitAmount', 0.0),
                'account_id': account.id,
                'xero_lineitem_id': line.get('LineItemID'),
            }))
        

        due_date_str = xero_invoice_data.get('DueDateString', '').split('T')[0]
        update_vals = {
            'invoice_line_ids': invoice_line_ids,
            'invoice_date_due': due_date_str if due_date_str else None,
        }
        
        odoo_invoice.write(update_vals)
        return
    
    
    def _export_odoo_invoices(self):
        """
        Finds all posted Odoo invoices without a xero_invoice_id, creates them in Xero,
        and returns a dictionary of statistics.
        """
        _logger.info("Starting export of Odoo invoices to Xero.")
        
        invoices_to_sync = self.env['account.move'].search([
            ('xero_invoice_id', '=', False),
            ('state', '=', 'posted'),
            ('move_type', 'in', ['out_invoice', 'in_invoice'])
        ])
        _logger.info(f"Found {len(invoices_to_sync)} invoices to export.")
    
        # Rename for consistency with the return dictionary
        created_count = 0
        
        for odoo_invoice in invoices_to_sync:
            if not odoo_invoice.partner_id.xero_contact_id:
                _logger.warning(f"Skipping invoice {odoo_invoice.name} - Partner not synced.")
                continue

            payload = self._prepare_xero_invoice_payload(odoo_invoice)
            
            # Defensive check: skip invoices that have no valid lines
            if not payload['Invoices'][0]['LineItems']:
                _logger.warning(f"Skipping invoice {odoo_invoice.name} - No valid lines to export.")
                continue
            
            response_data, error = self._make_xero_request('/Invoices', method='POST', json_data=payload)
            
            if error:
                _logger.error(f"Failed to export invoice {odoo_invoice.name}. Error: {error}")
                continue

            if response_data.get('Invoices'):
                new_xero_id = response_data['Invoices'][0]['InvoiceID']
                odoo_invoice.write({'xero_invoice_id': new_xero_id})
                created_count += 1
                
        _logger.info(f"Invoice export complete. Created: {created_count} new invoices.")

        # <<< CHANGE: Return a dictionary with the results for the notification system >>>
        return {'created': created_count, 'updated': 0}

    def _prepare_xero_invoice_payload(self, odoo_invoice):
        """
        Takes an Odoo account.move record and returns a dictionary formatted for the Xero API,
        now including support for discounts and item codes.
        """
        type_mapping = {
            'out_invoice': 'ACCREC',
            'in_invoice': 'ACCPAY',
        }
        
        # import pdb;pdb.set_trace()
        
        line_items = []
        for line in odoo_invoice.invoice_line_ids:
            # if line.display_type:
            #     continue
                
            line_data = {
                'Description': line.name,
                'Quantity': line.quantity,
                'UnitAmount': line.price_unit,
                'AccountCode': line.account_id.code,
                'TaxAmount':line.tax_ids.amount or 0,
            }
            

            # if line.product_id and line.product_id.default_code:
            #     line_data['ItemCode'] = line.product_id.default_code

            # if line.tax_ids:
            #         line_data['TaxType'] = line.tax_ids[0].name
                
    
            if line.discount:
                line_data['DiscountRate'] = line.discount

            line_items.append(line_data)
            
            
        payload = {
                'Invoices': [{
                    'Type': type_mapping.get(odoo_invoice.move_type),
                    'Contact': {
                        'ContactID': odoo_invoice.partner_id.xero_contact_id
                    },
                    'DateString': odoo_invoice.invoice_date.strftime('%Y-%m-%d') if odoo_invoice.invoice_date else '',
                    'DueDateString': odoo_invoice.invoice_date_due.strftime('%Y-%m-%d') if odoo_invoice.invoice_date_due else '',
                    # 'InvoiceNumber': odoo_invoice.name,
                    'Reference': odoo_invoice.ref or '',
                    'Status': 'AUTHORISED',
                    'LineItems': line_items,
                    # 'LineAmountTypes': 'Exclusive',
                }]
              }
        return payload



#================== xero product  import export =======================================


    def _export_odoo_products(self):
        """
        Finds all Odoo products without a xero_item_id and creates them in Xero.
        """
        _logger.info("Starting export of Odoo products to Xero.")

        # import pdb; pdb.set_trace
        
        products_to_sync = self.env['product.product'].search([('xero_item_id', '=', False)])
        
        
        synced_count = 0
        
        for odoo_product in products_to_sync:
            if not odoo_product.default_code:
                _logger.warning(f"Skipping product '{odoo_product.name}' - it has no Internal Reference (Code).")
                continue

            # Basic payload for all item types
            payload = {
                'Code': odoo_product.default_code,
                'Name': odoo_product.name,
                'Description': odoo_product.description_sale or '',
                'PurchaseDescription': odoo_product.description_purchase or '',
            }
            
            # Handle Tracked (Storable) vs. Untracked (Consumable/Service) items
            if odoo_product.type == 'product': # This is a Tracked Item
                # For tracked items, we need inventory and cost of goods sold accounts
                asset_account = odoo_product.categ_id.property_stock_valuation_account_id
                cogs_account = odoo_product.categ_id.property_account_expense_categ_id
                
                if not asset_account or not cogs_account:
                    _logger.warning(f"Skipping tracked product '{odoo_product.name}' - its category is missing an Inventory or COGS account.")
                    continue

                payload['InventoryAssetAccountCode'] = asset_account.code
                payload['PurchaseDetails'] = {'COGSAccountCode': cogs_account.code}
                payload['SalesDetails'] = {'UnitPrice': odoo_product.list_price}

            else: # This is an Untracked Item (Consumable or Service)
                payload['PurchaseDetails'] = {'UnitPrice': odoo_product.standard_price}
                payload['SalesDetails'] = {'UnitPrice': odoo_product.list_price}

            # Use POST to create the new item in Xero
            response_data, error = self._make_xero_request('/Items', method='POST', json_data=payload)
            
            if error:
                _logger.error(f"Failed to export product {odoo_product.default_code}. Error: {error}")
                continue

            if response_data.get('Items'):
                new_xero_id = response_data['Items'][0]['ItemID']
                odoo_product.write({'xero_item_id': new_xero_id})
                synced_count += 1
                
        _logger.info(f"Product export complete. Synced: {synced_count} new products.")
        return {'created': synced_count, 'updated': 0}
        
    
    # You can replace your existing _import_xero_items with these three functions

    def _prepare_product_vals(self, xero_item):
        """Helper function to map Xero item data to Odoo product values."""
        if xero_item.get('IsTrackedAsInventory'):
            odoo_product_type = 'consu'  # Storable Product
        else:
            odoo_product_type = 'service'    # Consumable

        return {
            'name': xero_item.get('Name'),
            'default_code': xero_item.get('Code'),
            'list_price': xero_item.get('SalesDetails', {}).get('UnitPrice', 0.0),
            'standard_price': xero_item.get('PurchaseDetails', {}).get('UnitPrice', 0.0),
            'description_sale': xero_item.get('Description'),
            'description_purchase': xero_item.get('PurchaseDescription'),
            'type': odoo_product_type,
            'xero_item_id': xero_item.get('ItemID'),
        }

    def _find_odoo_product_for_sync(self, item_code, xero_item_id):
        """Helper function to find a matching Odoo product."""
        Product = self.env['product.product']
        # Prioritize finding by the unique Xero ID
        product = Product.search([('xero_item_id', '=', xero_item_id)], limit=1)
        if not product:
            # Fallback to the user-defined code
            product = Product.search([('default_code', '=', item_code)], limit=1)
        return product

    def _import_xero_items(self):
        """
        Fetches all items from Xero and creates or updates them in Odoo.
        """
        _logger.info("Starting sync of Xero Items to Odoo Products.")
        # import pdb; pdb.set_trace()
        
        response_data, error = self._make_xero_request('/Items')

        xero_item = response_data.get('Items', [])
        
        if error:
            _logger.error(f"Failed to fetch items from Xero: {error}")
            return False

        created_count = 0
        updated_count = 0
        
        for xero_item in response_data.get('Items', []):
            item_code = xero_item.get('Code')
            xero_item_id = xero_item.get('ItemID')
            if not item_code or not xero_item_id:
                continue
            
            # 1. Find a matching product
            existing_product = self._find_odoo_product_for_sync(item_code, xero_item_id)
            
            # 2. Prepare the data values
            vals = self._prepare_product_vals(xero_item)

            # 3. Create or Update
            if existing_product:
                existing_product.write(vals)
                updated_count += 1
            else:
                self.env['product.product'].create(vals)
                created_count += 1
        
        _logger.info(f"Item sync complete. Created: {created_count}, Updated: {updated_count}.")
        return {'created': created_count, 'updated': updated_count}

    


#====================== Pyments sync =============================#

    def _import_xero_payments(self):
        """Fetches payments from Xero, creates them in Odoo, and returns stats."""
        _logger.info("Starting import of Xero payments.")
        
        response_data, error = self._make_xero_request('/Payments')
        if error:
            _logger.error(f"Failed to fetch payments from Xero: {error}")
            return {'created': 0, 'updated': 0}

        created_count = 0
        for xero_payment in response_data.get('Payments', []):
            xero_payment_id = xero_payment.get('PaymentID')

            if self.env['account.payment'].search_count([('xero_payment_id', '=', xero_payment_id)]) > 0:
                continue
                
            xero_invoice_id = xero_payment.get('Invoice', {}).get('InvoiceID')
            odoo_invoice = self.env['account.move'].search([('xero_invoice_id', '=', xero_invoice_id)], limit=1)
            if not odoo_invoice:
                _logger.warning(f"Skipping Xero payment {xero_payment_id} - cannot find linked invoice.")
                continue
                
            # FIX: Improved and more reliable journal search
            xero_bank_account_code = xero_payment.get('Account', {}).get('Code')
            odoo_journal = self.env['account.journal'].search([
                ('type', '=', 'bank'),
                ('default_account_id.code', '=', xero_bank_account_code)
            ], limit=1)

            if not odoo_journal:
                _logger.warning(f"Skipping Xero payment {xero_payment_id} - cannot find Bank Journal for account code {xero_bank_account_code}.")
                continue

            payment_date = xero_payment.get('DateString', '').split('T')[0]
            
            payment_vals = {
                'date': payment_date or None, # FIX: Added the date back
                'amount': xero_payment.get('Amount'),
                'payment_type': 'inbound' if odoo_invoice.move_type == 'out_invoice' else 'outbound',
                'partner_type': 'customer' if odoo_invoice.move_type == 'out_invoice' else 'supplier',
                'partner_id': odoo_invoice.partner_id.id,
                'journal_id': odoo_journal.id,
                'ref': f"Payment for {odoo_invoice.name}",
                'xero_payment_id': xero_payment_id,
            }
            new_payment = self.env['account.payment'].create(payment_vals)
            new_payment.action_post()
            
            # FIX: Re-enabled reconciliation to mark the invoice as paid
            dest_line = new_payment.line_ids.filtered(lambda line: line.account_id == odoo_invoice.account_id)
            if dest_line:
                odoo_invoice.js_assign_outstanding_line(dest_line.id)
            created_count += 1

        _logger.info(f"Payment import complete. Created: {created_count} new payments.")
        
        # CHANGE: Return stats for the notification system
        return {'created': created_count, 'updated': 0}
        

    def _export_odoo_payments(self):
        """ Export eligible Odoo payments to Xero """
      
        
        Payment = self.env['account.payment']
        payments = Payment.search([
            ('xero_payment_id', '=', False),
           
        ])
        
        _logger.info(f"Found {len(payments)} Odoo payments to export.")

        synced_count = 0
      
        for payment in payments:
            # Check linked invoice
            if payment.reconciled_invoice_ids:
                invoice = payment.reconciled_invoice_ids[0]
                if not invoice.xero_invoice_id:
                    _logger.warning(
                        f"Skipping payment {payment.name} - linked invoice {invoice.name} is not synced."
                    )
                    continue

            # Build payment payload
            # print("8888888888", invoice.xero_invoice_id)
            formatted_date = payment.date.strftime("%Y-%m-%d")
            amount =  payment.amount
            # import pdb; pdb.set_trace()

            payload ={
                        "Payments": [
                            {
                                "Invoice": {
                                    "InvoiceID": invoice.xero_invoice_id,
                                    "Status": "AUTHORISED"
                                },
                                "Account": {
                                    "AccountID": "a7a557a1-23fd-46a0-8781-686bb0b4d064"
                                },
                                "Date":"2025-09-16",
                                "Amount": amount ,           
                                }

                            
                        ]

                   }             

            # Send payment to Xero
            response, error = self._make_xero_request(
                "/Payments", method="POST", json_data=payload
            )


            if error:
                error_msg = error
                if isinstance(error, dict) and error.get("Elements"):
                    error_msg = error["Elements"]
                _logger.error(
                    f"Failed to export payment {payment.name} to Xero. Error: {error_msg}"
                )
                continue


            # Mark as synced
            
            _logger.info(f"Payment {payment.name} exported successfully to Xero.")
            synced_count += 1

        _logger.info(f"Payment export complete. Synced: {synced_count} new payments.")
        return {'created': synced_count, 'updated': 0}





#================== generic method to show the notification  success and  failed  =====================
    

    def _show_sync_notification(self, object_name, results):
        """
        Takes the results of a sync and returns a client action to show a notification.
        'results' should be a dictionary e.g. {'created': 5, 'updated': 10}
        """
        created = results.get('created', 0)
        updated = results.get('updated', 0)
        
        message = f"Successfully synced {object_name}: {created} created, {updated} updated."
        
        # This returns a dictionary that Odoo's web client understands
        # as a command to show a "rainbow man" success notification.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Synchronization Complete",
                'message': message,
                'type': 'success', # Can be 'success', 'warning', 'danger'
                'sticky': False,
            }
        }