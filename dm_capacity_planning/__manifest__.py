# -*- coding: utf-8 -*-
{
    'name': 'DM Capacity Planning',
    'version': '17.0.1.1.0',  # Phase 2 - Minor increment
    'category': 'Manufacturing',
    'summary': 'Production capacity planning with time-based tracking, TEU standardization, and constraint checking',
    'description': """
Production Capacity Planning Module - Phase 2
==============================================

Advanced vendor capacity management with:

Phase 2 Features (NEW):
* Full capacity compliance checking algorithm
* Month-level capacity aggregation
* Multi-constraint validation (product/category limits)
* Detailed violation messages
* Visual capacity check wizard with progress bars
* Enhanced production run views with utilization metrics

Phase 1 Features:
* Time-based capacity tracking (multiple periods per vendor)
* TEU standardization across container types
* Automatic capacity conversion (containers ↔ TEU)
* Optional product/category-specific constraints
* Production run capacity integration
* Real-time capacity status indicators

Business Value:
* Prevent vendor over-commitment
* Visual capacity utilization tracking
* Product-specific capacity constraints
* Historical capacity tracking
* Foundation for advanced planning tools
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'license': 'LGPL-3',
    'depends': [
        'dm_base',
        'dm_master_data',
        'dm_deal',
        'dm_production',
    ],
    'data': [
        # Security
        'security/capacity_planning_security.xml',
        'security/ir.model.access.csv',
        
        # Wizard Views (Phase 2)
        'wizards/dm_capacity_check_wizard_views.xml',
        
        # Views
        'views/dm_vendor_capacity_views.xml',
        'views/dm_vendor_capacity_constraint_views.xml',
        'views/res_partner_views.xml',
        'views/dm_production_run_views.xml',
        'views/dm_production_allocation_board_actions.xml',  # ADD THIS (actions first!)
        'views/dm_production_allocation_board_views.xml',    # ADD THIS (then views)
        'views/capacity_planning_menus.xml',  # This now includes allocation board menu
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}