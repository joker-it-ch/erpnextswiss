// Copyright (c) 2021, libracore (https://www.libracore.com) and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Annual Salary Sheet"] = {
    "filters": [
        {
            'fieldname': 'fiscal_year',
            'label': __("Fiscal Year"),
            'fieldtype': 'Link',
            'options': 'Fiscal Year',
            'default': frappe.defaults.get_global_default('fiscal_year'),
            'reqd': 1
        },
        {
            'fieldname': 'employee',
            'label': __("Employee"),
            'fieldtype': 'Link',
            'options': 'Employee',
            'reqd': 1
        }
    ]
};
