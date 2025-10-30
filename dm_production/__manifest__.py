{
    'name': 'DM Production Management',
    'version': '17.0.3.1.0',  # Phase 1 - Production Lines
    'category': 'Manufacturing',
    'summary': 'Production run management with line-level tracking',
    'description': """
        DonnaMello Production Management - Phase 1
        ==========================================
        
        Production allocation and line-level tracking.
        
        Phase 1 New Features:
        ---------------------
        * Production line model (dm.production.line)
        * Line-level quantity tracking (ordered vs produced)
        * Package-native variance calculations
        * TEU and container totals per line
        * Auto-creation from deal lines on allocation
        * Aggregate totals in production run
        
        Core Features:
        --------------
        * Production Run model (allocation target)
        * Deal-to-Production allocation
        * TEU and container totals
        * Capacity validation integration
        * Production allocation wizard (bulk)
        * Extends dm_deal with production fields
        * Extends dm_allocation with production reference
        
        Integration:
        ------------
        * Works standalone or with dm_capacity_planning
        * Graceful degradation when capacity module not installed
        * Package-native TEU calculations
        
        Version: 3.1.0 (Phase 1 Complete)
        Status: Production Ready
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'dm_deal',
        'dm_master_data',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        
        # Views - Order matters!
        'views/dm_production_line_views.xml',       # NEW: Production lines
        'views/dm_production_run_views.xml',        # Core PR views (modified)
        'views/dm_deal_unallocated_views.xml',      # Unallocated deals view + action
        'views/dm_deal_production_views.xml',       # Deal extensions
        
        # Wizards
        'wizards/production_allocation_wizard_views.xml',  # Bulk allocation
        'wizards/quick_allocate_wizard_views.xml',         # Quick allocation
        
        # Data
        'data/production_server_actions.xml',       # Server actions
        
        # Menus - MUST BE LAST (after all actions defined)
        'views/production_menus.xml',               # Menu structure
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}