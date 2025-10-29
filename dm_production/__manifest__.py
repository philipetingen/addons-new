{
    'name': 'DM Production Management',
    'version': '17.0.2.0.0',  # Phase 3A - Major increment (new features)
    'category': 'Manufacturing',
    'summary': 'Production run management with allocation cockpit and capacity integration',
    'description': """
        DonnaMello Production Management - Phase 3A Enhanced
        ====================================================
        
        Production allocation and planning with visual cockpit.
        
        Phase 3A New Features:
        ----------------------
        * Unallocated Deals view with grouping and filters
        * Quick allocation wizard with capacity preview
        * Enhanced production run views with capacity utilization
        * Restructured menu for better navigation
        * Add/remove deals from production runs
        * Color-coded capacity status
        
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
        
        Version: 2.0.0 (Phase 3A)
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
        'views/dm_production_run_views.xml',        # Core PR views
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