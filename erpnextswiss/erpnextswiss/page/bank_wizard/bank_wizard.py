# -*- coding: utf-8 -*-
# Copyright (c) 2017-2018, libracore and contributors
# License: AGPL v3. See LICENCE

from __future__ import unicode_literals
import frappe
from frappe import throw, _
import hashlib
import json
from bs4 import BeautifulSoup
import ast
import cgi                              # (used to escape utf-8 to html)
#from erpnextswiss.erpnextswiss.page.bankimport.bankimport import create_reference

# this function tries to match the amount to an open sales invoice
#
# returns the sales invoice reference (name string) or None
def match_by_amount(amount):
    # get sales invoices
    sql_query = ("SELECT `name` " +
                "FROM `tabSales Invoice` " +
                "WHERE `docstatus` = 1 " + 
                "AND `grand_total` = {0} ".format(amount) + 
                "AND `status` != 'Paid'")
    open_sales_invoices = frappe.db.sql(sql_query, as_dict=True)
    if open_sales_invoices:
        if len(open_sales_invoices) == 1:
            # found exactly one match
            return open_sales_invoices[0].name
        else:
            # multiple sales invoices with this amount found
            return None
    else:
        # no open sales invoice with this amount found
        return None
        
# this function tries to match the comments to an open sales invoice
# 
# returns the sales invoice reference (name sting) or None
def match_by_comment(comment):
    # get sales invoices (submitted, not paid)
    sql_query = ("SELECT `name` " +
                "FROM `tabSales Invoice` " +
                "WHERE `docstatus` = 1 " + 
                "AND `status` != 'Paid'")
    open_sales_invoices = frappe.db.sql(sql_query, as_dict=True)
    if open_sales_invoices:
        # find sales invoice referernce in the comment
        for reference in open_sales_invoices.name:
            if reference in comment:
                # found a match
                return reference
    return None

# find unpaid invoices for a customer
#
# returns a dict (name) of sales invoice references or None
def get_unpaid_sales_invoices_by_customer(customer):
    # get sales invoices (submitted, not paid)
    sql_query = ("SELECT `name` " +
                "FROM `tabSales Invoice` " +
                "WHERE `docstatus` = 1 " + 
                "AND `customer` = '{0}' ".format(customer) +
                "AND `status` != 'Paid'")
    open_sales_invoices = frappe.db.sql(sql_query, as_dict=True)
    return open_sales_invoices   

# create a payment entry
def create_payment_entry(date, to_account, received_amount, transaction_id, remarks, auto_submit=False):
    # get default customer
    default_customer = get_default_customer()
    if not frappe.db.exists('Payment Entry', {'reference_no': transaction_id}):
        # create new payment entry
        new_payment_entry = frappe.get_doc({'doctype': 'Payment Entry'})
        new_payment_entry.payment_type = "Receive"
        new_payment_entry.party_type = "Customer";
        new_payment_entry.party = default_customer
        # date is in DD.MM.YYYY
        new_payment_entry.posting_date = date
        new_payment_entry.paid_to = to_account
        new_payment_entry.received_amount = received_amount
        new_payment_entry.paid_amount = received_amount
        new_payment_entry.reference_no = transaction_id
        new_payment_entry.reference_date = date
        new_payment_entry.remarks = remarks
        inserted_payment_entry = new_payment_entry.insert()
        if auto_submit:
            new_payment_entry.submit()
        frappe.db.commit()
        return inserted_payment_entry
    else:
        return None
    
# creates the reference record in a payment entry
def create_reference(payment_entry, sales_invoice):
    # create a new payment entry reference
    reference_entry = frappe.get_doc({"doctype": "Payment Entry Reference"})
    reference_entry.parent = payment_entry
    reference_entry.parentfield = "references"
    reference_entry.parenttype = "Payment Entry"
    reference_entry.reference_doctype = "Sales Invoice"
    reference_entry.reference_name = sales_invoice
    reference_entry.total_amount = frappe.get_value("Sales Invoice", sales_invoice, "base_grand_total")
    reference_entry.outstanding_amount = frappe.get_value("Sales Invoice", sales_invoice, "outstanding_amount")
    paid_amount = frappe.get_value("Payment Entry", payment_entry, "paid_amount")
    if paid_amount > reference_entry.outstanding_amount:
        reference_entry.allocated_amount = reference_entry.outstanding_amount
    else:
        reference_entry.allocated_amount = paid_amount
    reference_entry.insert();
    return
    
def log(comment):
	new_comment = frappe.get_doc({"doctype": "Log"})
	new_comment.comment = comment
	new_comment.insert()
	return new_comment

# converts a parameter to a bool
def assert_bool(param):
    result = param
    if result == 'false':
        result = False
    elif result == 'true':
        result = True	 
    return result  

def get_default_customer():
    default_customer = frappe.get_value("ERPNextSwiss Settings", "ERPNextSwiss Settings", "default_customer")
    if not default_customer:
        default_customer = "Guest"
    return default_customer

@frappe.whitelist()
def get_bank_accounts():
    accounts = frappe.get_list('Account', filters={'account_type': 'Bank', 'is_group': 0}, fields=['name'])
    selectable_accounts = []
    for account in accounts:
		selectable_accounts.append(account.name)    
    
    # frappe.throw(selectable_accounts)
    return {'accounts': selectable_accounts }

@frappe.whitelist()
def get_intermediate_account():
    account = frappe.get_value('ERPNextSwiss Settings', 'ERPNextSwiss Settings', 'intermediate_account')
    return {'account': account or "" }

@frappe.whitelist()
def get_default_customer():
    customer = frappe.get_value('ERPNextSwiss Settings', 'ERPNextSwiss Settings', 'default_customer')
    return {'customer': customer or "" }
    
@frappe.whitelist()
def get_default_supplier():
    supplier = frappe.get_value('ERPNextSwiss Settings', 'ERPNextSwiss Settings', 'default_supplier')
    return {'supplier': supplier or "" }
    
@frappe.whitelist()
def get_receivable_account(company=None):
    if not company:
        company = get_first_company()
    account = frappe.get_value('Company', company, 'default_receivable_account')
    return {'account': account or "" }

@frappe.whitelist()
def get_payable_account(company=None):
    if not company:
        company = get_first_company()
    account = frappe.get_value('Company', company, 'default_payable_account')
    return {'account': account or "" }

def get_first_company():
    companies = frappe.get_all("Company", filters=None, fields=['name'])
    return companies[0]['name']

@frappe.whitelist()
def read_camt053(content, account):
    #read_camt_transactions_re(content)
    soup = BeautifulSoup(content, 'lxml')
    
    # general information
    try:
        #iban = doc['Document']['BkToCstmrStmt']['Stmt']['Acct']['Id']['IBAN']
        iban = soup.document.bktocstmrstmt.stmt.acct.id.iban.get_text()
    except:
        # node not found, probably wrong format
        return { "message": _("Unable to read structure. Please make sure that you have selected the correct format."), "records": None }
            
    # transactions
    #new_payment_entries = read_camt_transactions(doc['Document']['BkToCstmrStmt']['Stmt']['Ntry'], bank, account, auto_submit)
    entries = soup.find_all('ntry')
    transactions = read_camt_transactions(entries, account)
    
    return { 'transactions': transactions } 
    
def read_camt_transactions(transaction_entries, account):
    txns = []
    for entry in transaction_entries:
        entry_soup = BeautifulSoup(unicode(entry), 'lxml')
        date = entry_soup.bookgdt.dt.get_text()
        transactions = entry_soup.find_all('txdtls')
        # fetch entry amount as fallback
        entry_amount = float(entry_soup.amt.get_text())
        entry_currency = entry_soup.amt['ccy']
        for transaction in transactions:
            transaction_soup = BeautifulSoup(unicode(transaction), 'lxml')
            # --- find transaction type: paid or received: (DBIT: paid, CRDT: received)
            try:
                credit_debit = transaction_soup.cdtdbtind.get_text()
            except:
                # fallback to entry indicator
                credit_debit = entry_soup.cdtdbtind.get_text()
            
            #try:
            # --- find unique reference
            try:
                # try to use the account service reference
                unique_reference = transaction_soup.txdtls.refs.acctsvcrref.get_text()
            except:
                # fallback: use tx id
                try:
                    unique_reference = transaction_soup.txid.get_text()
                except:
                    # fallback to pmtinfid
                    try:
                        unique_reference = transaction_soup.pmtinfid.get_text()
                    except:
                        # fallback to ustrd
                        unique_reference = transaction_soup.ustrd.get_text()
            # --- find amount and currency
            try:
                amount = float(transaction_soup.txdtls.amt.get_text())
                currency = transaction_soup.txdtls.amt['ccy']
            except:
                # fallback to amount from entry level
                amount = entry_amount
                currency = entry_currency
            try:
                # --- find party IBAN
                if credit_debit == "DBIT":
                    # use RltdPties:Cdtr
                    party_soup = BeautifulSoup(unicode(transaction_soup.txdtls.rltdpties.cdtr)) 
                    try:
                        party_iban = transaction_soup.cdtracct.id.iban.get_text()
                    except:
                        party_iban = ""
                else:
                    # CRDT: use RltdPties:Dbtr
                    party_soup = BeautifulSoup(unicode(transaction_soup.txdtls.rltdpties.dbtr)) 
                    try:
                        party_iban = transaction_soup.dbtracct.id.iban.get_text()
                    except:
                        party_iban = ""
                try:
                    party_name = party_soup.nm.get_text()
                    if party_soup.strtnm:
                        # parse by street name, ...
                        try:
                            street = party_soup.strtnm.get_text()
                            try:
                                street_number = party_soup.bldgnb.get_text()
                                address_line = "{0} {1}".format(street, street_number)
                            except:
                                address_line = street
                                
                        except:
                            address_line = ""
                        try:
                            plz = party_soup.pstcd.get_text()
                        except:
                            plz = ""
                        try:
                            town = party_soup.twnnm.get_text()
                        except:
                            town = ""
                        address_line2 = "{0} {1}".format(plz, town)
                    else:
                        # parse by address lines
                        try:
                            address_lines = party_soup.find_all("adrline")
                            address_line1 = address_lines[0].get_text()
                            address_line2 = address_lines[1].get_text()
                        except:
                            # in case no address is provided
                            address_line1 = ""
                            address_line2 = ""                            
                except:
                    # party is not defined (e.g. DBIT from Bank)
                    party_name = "not found"
                    address_line1 = ""
                    address_line2 = ""
                try:
                    country = party_soup.ctry.get_text()
                except:
                    country = ""
                if (address_line1 != "") and (address_line2 != ""):
                    party_address = "{0}, {1}, {2}".format(
                        address_line1,
                        address_line2,
                        country)
                elif (address_line1 != ""):
                    party_address = "{0}, {1}".format(address_line1, country)
                else:
                    party_address = "{0}".format(country)
            except:
                # key related parties not found / no customer info
                party_name = ""
                party_address = ""
                party_iban = ""
            try:
                charges = float(transaction_soup.chrgs.ttlchrgsandtaxamt[text])
            except:
                charges = 0.0

            try:
                # try to find ESR reference
                transaction_reference = transaction_soup.rmtinf.strd.cdtrrefinf.ref.get_text()
            except:
                try:
                    # try to find a user-defined reference (e.g. SINV.)
                    transaction_reference = transaction_soup.rmtinf.ustrd.get_text()
                except:
                    try:
                        # try to find an end-to-end ID
                        transaction_reference = transaction_soup.cdtdbtind.get_text() 
                    except:
                        transaction_reference = unique_reference
            # debug: show collected record in error log
            #frappe.log_error("type:{type}\ndate:{date}\namount:{currency} {amount}\nunique ref:{unique}\nparty:{party}\nparty address:{address}\nparty iban:{iban}\nremarks:{remarks}".format(
            #    type=credit_debit, date=date, currency=currency, amount=amount, unique=unique_reference, party=party_name, address=party_address, iban=party_iban, remarks=transaction_reference))
            
            # check if this transaction is already recorded
            match_payment_entry = frappe.get_all('Payment Entry', filters={'reference_no': unique_reference}, fields=['name'])
            if match_payment_entry:
                frappe.log_error("Transaction {0} is already imported in {1}.".format(unique_reference, match_payment_entry[0]['name']))
            else:
                # try to find matching parties & invoices
                party_match = None
                invoice_matches = None
                matched_amount = 0.0
                if credit_debit == "DBIT":
                    # suppliers 
                    match_suppliers = frappe.get_all("Supplier", filters={'supplier_name': party_name}, fields=['name'])
                    if match_suppliers:
                        party_match = match_suppliers[0]['name']
                    # purchase invoices
                    possible_pinvs = frappe.get_all("Purchase Invoice", filters=[['grand_total', '=', amount], ['outstanding_amount', '>', 0]], fields=['name', 'supplier', 'outstanding_amount'])
                    if possible_pinvs:
                        invoice_matches = []
                        for pinv in possible_pinvs:
                            if pinv['name'] in transaction_reference:
                                invoice_matches.append(pinv['name'])
                                # override party match in case there is one from the sales invoice
                                party_match = pinv['supplier']
                                # add total matched amount
                                matched_amount += float(pinv['outstanding_amount'])
                                
                else:
                    # customers & sales invoices
                    match_customers = frappe.get_all("Customer", filters={'customer_name': party_name}, fields=['name'])
                    if match_customers:
                        party_match = match_customers[0]['name']
                    # sales invoices
                    possible_sinvs = frappe.get_all("Sales Invoice", filters=[['outstanding_amount', '>', 0]], fields=['name', 'customer', 'outstanding_amount'])
                    if possible_sinvs:
                        invoice_matches = []
                        for sinv in possible_sinvs:
                            if sinv['name'] in transaction_reference:
                                invoice_matches.append(sinv['name'])
                                # override party match in case there is one from the sales invoice
                                party_match = sinv['customer']
                                # add total matched amount
                                matched_amount += float(sinv['outstanding_amount'])
                                
                # reset invoice matches in case there are no matches
                try:
                    if len(invoice_matches) == 0:
                        invoice_matches = None
                except:
                    pass                                                                                                
                new_txn = {
                    'txid': len(txns),
                    'date': date,
                    'currency': currency,
                    'amount': amount,
                    'party_name': party_name,
                    'party_address': party_address,
                    'credit_debit': credit_debit,
                    'party_iban': party_iban,
                    'unique_reference': unique_reference,
                    'transaction_reference': transaction_reference,
                    'party_match': party_match,
                    'invoice_matches': invoice_matches,
                    'matched_amount': matched_amount
                }
                txns.append(new_txn)    

    return txns

@frappe.whitelist()
def make_payment_entry(amount, date, reference_no, paid_from=None, paid_to=None, type="Receive", 
    party=None, party_type=None, references=None, remarks=None, auto_submit=False):
    # assert list
    if references:
        references = ast.literal_eval(references)
    if str(auto_submit) == "1":
        auto_submit = True
    if type == "Receive":
        # receive
        payment_entry = frappe.get_doc({
            'doctype': 'Payment Entry',
            'payment_type': 'Receive',
            'party_type': party_type,
            'party': party,
            'paid_to': paid_to,
            'paid_amount': float(amount),
            'received_amount': float(amount),
            'reference_no': reference_no,
            'reference_date': date,
            'posting_date': date,
            'remarks': remarks,
            'camt_amount': float(amount)
        })
    elif type == "Pay":
        # pay
        payment_entry = frappe.get_doc({
            'doctype': 'Payment Entry',
            'payment_type': 'Pay',
            'party_type': party_type,
            'party': party,
            'paid_from': paid_from,
            'paid_amount': float(amount),
            'received_amount': float(amount),
            'reference_no': reference_no,
            'reference_date': date,
            'posting_date': date,
            'remarks': remarks,
            'camt_amount': float(amount)
        })
    else:
        # internal transfer (against intermediate account)
        payment_entry = frappe.get_doc({
            'doctype': 'Payment Entry',
            'payment_type': 'Internal Transfer',
            'paid_from': paid_from,
            'paid_to': paid_to,
            'paid_amount': float(amount),
            'received_amount': float(amount),
            'reference_no': reference_no,
            'reference_date': date,
            'posting_date': date,
            'remarks': remarks,
            'camt_amount': float(amount)
        })    
    new_entry = payment_entry.insert()
    # add references after insert (otherwise they are overwritten)
    if references:
        for reference in references:
            create_reference(new_entry.name, reference)
    # automatically submit if enabled
    if auto_submit:
        matched_entry = frappe.get_doc("Payment Entry", new_entry.name)
        matched_entry.submit()
    return new_entry.name

# creates the reference record in a payment entry
def create_reference(payment_entry, sales_invoice):
    # create a new payment entry reference
    reference_entry = frappe.get_doc({"doctype": "Payment Entry Reference"})
    reference_entry.parent = payment_entry
    reference_entry.parentfield = "references"
    reference_entry.parenttype = "Payment Entry"
    reference_entry.reference_doctype = "Sales Invoice"
    reference_entry.reference_name = sales_invoice
    reference_entry.total_amount = frappe.get_value("Sales Invoice", sales_invoice, "base_grand_total")
    reference_entry.outstanding_amount = frappe.get_value("Sales Invoice", sales_invoice, "outstanding_amount")
    paid_amount = frappe.get_value("Payment Entry", payment_entry, "paid_amount")
    if paid_amount > reference_entry.outstanding_amount:
        reference_entry.allocated_amount = reference_entry.outstanding_amount
    else:
        reference_entry.allocated_amount = paid_amount
    reference_entry.insert();
    # update unallocated amount
    payment_record = frappe.get_doc("Payment Entry", payment_entry)
    payment_record.unallocated_amount -= reference_entry.allocated_amount
    payment_record.save()
    return

