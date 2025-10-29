{
    'name': 'DM Deal Management',
    'version': '17.0.2.3.0',
    'category': 'Sales/Sales',
    'summary': 'Core deal management with allocation infrastructure',
    'description': """
        DonnaMello Deal Management Module - REFACTORED
        ==============================================
        
        CLEAN ARCHITECTURE: Production/Shipment Agnostic
        -------------------------------------------------
        
        Core deal management functionality with GENERIC allocation infrastructure.
        
        Production and Shipment specific features are now in separate modules:
        * dm_production - Production allocation, production runs
        * dm_shipment - Shipment allocation, container management
        
        Core Features:
        -------------
        * Customer PO# tracking (mandatory)
        * Deal template hierarchy (product → category → generic)
        * Package-native quantities with 6-decimal pricing
        * Three-layer date management (requested/current/actual)
        * SO/PO generation triggers
        * Price freeze after confirmation
        * Container type inheritance from products
        * Generic allocation tracking infrastructure
        
        Allocation Infrastructure Provided:
        -----------------------------------
        * dm.allocation model (state machine for allocation tracking)
        * allocation_ids (One2many to track all allocations)
        * allocation_status (computed: unallocated/partial/allocated)
        * allocation_count (number of active allocations)
        * action_deallocate_all() (cancel all allocations)
        * action_view_allocations() (view allocation history)
        
        Milestone Infrastructure Provided:
        ----------------------------------
        * Seven milestone date layers (requested/current/actual):
          - Order Confirmation
          - Production Start (infrastructure for dm_production)
          - Ready to Ship (RTS)
          - Loading
          - Vessel Departure (ETD)
          - Port Arrival (ETA)
          - Final Delivery
        * get_milestone_date() method (single source of truth)
        * CASCADE date management mixin
        
        Extension Pattern:
        ------------------
        dm_production and dm_shipment modules will:
        1. Inherit dm.deal model
        2. Add their specific fields (production_allocated, production_run_ids, etc.)
        3. Add their specific methods (action_allocate_to_production, etc.)
        4. Inherit views to add smart buttons and allocation wizards
        
        Version History:
        ----------------
        v2.3.0: MAJOR REFACTOR
        - Removed production/shipment specific code from core module
        - Cleaned allocation infrastructure to be generic
        - Removed allocation wizards (moved to dm_production/dm_shipment)
        - Simplified views to core functionality only
        - Production/shipment features will be added via module inheritance
        
        v2.2.2: Bug fix - Removed premature production/shipment UI references
        v2.2.1: Bug fix - Fixed display_name field in dm.allocation
        v2.2.0: Added smart currency/supplier lookup and validation
        v2.1.0: Fixed packaging references, removed redundant code
        v2.0.0: Initial allocation system implementation
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'dm_base',
        'dm_master_data',
        'dm_packaging',
        'dm_pricing',
        'sale',
        'purchase',
        'account',
        'product',
        'mail',
    ],
    'data': [
        'security/dm_deal_security.xml',
        'security/ir.model.access.csv',
        'data/dm_deal_sequence.xml',
        'data/deal_server_actions.xml',
        'views/dm_deal_template_views.xml',
        'views/dm_deal_views.xml',
        'views/dm_deal_line_views.xml',
        'views/dm_deal_allocation_views.xml',
        'wizards/deal_template_selection_wizard.xml',
        'wizards/deal_supplier_selection_wizard_views.xml',
        'wizards/deal_creation_wizard_views.xml',
        'views/dm_deal_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}