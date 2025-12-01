{
    'name': 'DonnaMello Financial Management',
    'version': '17.0.1.3.0',
    'category': 'Accounting/Accounting',
    'summary': 'Financial management - Phase 3 Invoice Generation Complete',
    'description': """
        DonnaMello Financial Management Module
        =======================================
        
        Version 1.3.0 - Phase 3 Invoice Generation Core:
        - Complete split invoice generation (product + service)
        - Pro-rata downpayment allocation by split %
        - Milestone-based due dates
        - Package-native loaded quantity basis
        - Logistics cost itemization in service invoice
        - Invoice-to-deal-to-shipment linking
        - Downpayment application tracking
        
        Version 1.2.0 - Phase 2 Shipment Financial Extension:
        - Logistics cost collection (freight, insurance, other)
        - dm.logistics.cost model for itemized costs
        - Shipment financial tab with cost entry
        - Total logistics cost computation
        
        Version 1.1.0 - Phase 1 Foundation Fixes:
        - Fixed field references (amount_untaxed_sale/purchase)
        - Removed duplicate fields (total_value/purchase_total)
        - Fixed module dependencies
        
        Features:
        - CAD-compliant payment milestones
        - Automated downpayment request management
        - Invoice split configuration (80/20 product/service)
        - Split invoice generation with actual loaded quantities
        - Pro-rata downpayment allocation
        - Logistics cost collection and tracking
        - Cash flow projections by deal
        - Integration with deal operational milestones
        - Complete invoice-deal-shipment traceability
        
        This module manages all financial aspects of deals including:
        - Payment term milestone configuration
        - Downpayment tracking for customers and suppliers
        - Automatic invoice generation with actual shipped quantities
        - Pro-rata downpayment allocation across split invoices
        - Logistics cost collection and tracking
        - Cash flow timeline visualization
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'dm_base',
        'dm_master_data',
        'dm_pricing',
        'dm_deal',
        'account',
        'mail',
    ],
    'data': [
        # Security
        'security/dm_financial_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/dm_financial_sequence.xml',
        
        # Views - Models
        'views/dm_payment_milestone_views.xml',
        'views/dm_downpayment_request_views.xml',
        'views/dm_invoice_split_config_views.xml',
        'views/dm_financial_deal_views.xml',
        'views/account_payment_views.xml',
        # 'views/account_move_views.xml',
        
        # Views - Wizards
        'wizards/dp_create_payment_wizard_views.xml',
        'wizards/dp_assign_wizard_views.xml',
        
        # Menu
        'views/dm_financial_menu.xml',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}