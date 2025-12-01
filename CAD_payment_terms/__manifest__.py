{
    'name': 'CAD Payment Terms',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Milestone-based payment terms with CAD compliance',
    'description': """
        CAD Payment Terms
        =================
        
        Extends standard Odoo payment terms with:
        - CAD (Cash Against Documents) compliance tracking
        - Milestone-based payment scheduling
        - Flexible timing (before/on/after milestone)
        - Downpayment detection and validation
        - Standard configuration templates
        
        Integration with dm.milestone.type from dm_master_data for:
        - Operational milestone references
        - Dynamic date calculation
        - Business-specific milestone mapping
        
        This module provides the foundation for milestone-based
        payment terms that can be used by any business process.
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'account',
        'mail',
        'dm_master_data',  # For dm.milestone.type
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_payment_term_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}