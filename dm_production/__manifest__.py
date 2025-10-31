{
    'name': 'DM Production Management',
    'version': '17.0.3.2.0',  # Phase 2 - Lot Management
    'category': 'Manufacturing',
    'summary': 'Production run management with line-level tracking and lot management',
    'description': """
        DonnaMello Production Management - Phase 2
        ==========================================
        
        Phase 2 New Features (v3.2.0):
        -------------------------------
        * Production lot model (dm.production.lot)
        * Lot wizard with smart auto-split
        * Strict quantity validation (total = produced)
        * Auto-expiry date calculation from product
        * Block RTS without complete lots
        * Full traceability: Deal → PR → Lot
        
        Phase 1 Features (v3.1.0):
        ---------------------------
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
        
        Version: 3.2.0 (Phase 2 Complete)
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
        
        
        # Wizards
        'wizards/production_lot_wizard_views.xml',         # NEW: Lot management
        'wizards/production_allocation_wizard_views.xml',  # Bulk allocation
        'wizards/quick_allocate_wizard_views.xml',         # Quick allocation

        # Views - Order matters!
        'views/dm_production_line_views.xml',       # Production lines
        'views/dm_production_run_views.xml',        # Core PR views
        'views/dm_deal_unallocated_views.xml',      # Unallocated deals view + action
        'views/dm_deal_production_views.xml',       # Deal extensions
        
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