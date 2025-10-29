{
    'name': 'DonnaMello Base',
    'version': '17.0.1.0.0',
    'category': 'DonnaMello/Foundation',
    'summary': 'Core mixins, utilities and CASCADE engine for DonnaMello Distribution System',
    'description': """
        DonnaMello Base Module
        ======================
        
        This module provides the foundation for the DonnaMello Distribution System:
        
        Core Features:
        --------------
        * CASCADE engine with loop prevention and logging
        * Package-native computation mixins
        * State transition validators
        * Error handling patterns
        * Batch processing utilities
        * Common field definitions
        
        Technical Patterns:
        ------------------
        * 6-decimal precision for pricing
        * Package quantity as primary UoM
        * Customer PO# tracking
        * Price per kg calculations
        * Virtual stock helpers
        
        This module must be installed before all other DonnaMello modules.
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'base',
        'mail',
        'product',
        'uom',
    ],
    'data': [
        'security/dm_security.xml',
        'security/ir.model.access.csv',
        'data/dm_sequence_data.xml',
        'data/dm_parameters.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}