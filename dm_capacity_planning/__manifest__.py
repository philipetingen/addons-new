# -*- coding: utf-8 -*-
{
    'name': 'DM Capacity Planning',
    'version': '17.0.2.0.0',  # Major cleanup - version 2.0
    'category': 'Manufacturing',
    'summary': 'Vendor capacity management with TEU standardization and constraint checking',
    'description': """
Production Capacity Planning Module
====================================

Core vendor capacity management features:

* Time-based capacity tracking (multiple periods per vendor)
* TEU standardization across container types
* Automatic capacity conversion (containers ↔ TEU)
* Optional product/category-specific constraints
* Capacity compliance checking algorithm
* Month-level capacity aggregation
* Multi-constraint validation

Business Value:
* Prevent vendor over-commitment
* Product-specific capacity constraints
* Historical capacity tracking
* Foundation for deal-level capacity validation
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'license': 'LGPL-3',
    'depends': [
        'dm_base',
        'dm_master_data',
    ],
    'data': [
        # Security
        'security/capacity_planning_security.xml',
        'security/ir.model.access.csv',
        
        # Wizard Views
        'wizards/dm_capacity_check_wizard_views.xml',
        
        # Views
        'views/dm_vendor_capacity_views.xml',
        'views/dm_vendor_capacity_constraint_views.xml',
        'views/res_partner_views.xml',
        'views/capacity_planning_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}