{
    'name': 'DonnaMello Financial Management',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Financial management with CAD payment terms, downpayments, and invoice splitting',
    'description': """
        DonnaMello Financial Management Module
        =======================================
        
        Features:
        - CAD-compliant payment milestones
        - Automated downpayment request management
        - Invoice split configuration (80/20 product/service)
        - Cash flow projections by deal
        - Integration with deal operational milestones
        
        This module manages all financial aspects of deals including:
        - Payment term milestone configuration
        - Downpayment tracking for customers and suppliers
        - Automatic invoice generation with actual shipped quantities
        - Pro-rata downpayment allocation
        - Cash flow timeline visualization
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'dm_base',
        'dm_master_data',
        'dm_pricing',
        'dm_deal',
        'dm_production',  
        'dm_shipment',    
        'account',
        'mail',
    ],
    'data': [
        # Security
        'security/dm_financial_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/dm_financial_sequence.xml',
        
        # Views
        'views/dm_payment_milestone_views.xml',
        'views/account_payment_term_views.xml',
        'views/dm_downpayment_request_views.xml',
        'views/dm_invoice_split_config_views.xml',
        'views/dm_cash_flow_views.xml',
        'views/dm_deal_views.xml',
        'views/dm_financial_menu.xml',
        
        # Wizards
        'wizards/dm_invoice_generation_wizard_views.xml',
        'wizards/dm_cash_flow_projection_wizard_views.xml',
        
        # Reports
        # 'reports/dm_financial_reports.xml',
        # 'reports/dm_cash_flow_report_template.xml',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}