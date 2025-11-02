{
    'name': 'DM Deal Management',
    'version': '17.0.3.0.0',
    'category': 'Sales/Sales',
    'summary': 'Deal management - restructured for Phase 4B',
    'description': """
        DonnaMello Deal Management Module - v3.0 RESTRUCTURED
        ====================================================
        
        MAJOR REFACTORING: Domain-Based File Organization
        ------------------------------------------------
        
        Module restructured for maintainability and Phase 4B readiness:
        * State machine merged and refined (added 'partial' and 'completed' states)
        * Phase 4B: Validation/Confirmation workflow refined (SO/PO creation deferred to confirmation)
        * Domain-based file splits for token efficiency
        * No functional changes - pure refactoring
        
        Core Features:
        -------------
        * Customer PO# tracking (mandatory)
        * Deal template hierarchy (product → category → generic)
        * Package-native quantities with 6-decimal pricing
        * Three-layer date management (requested/current/actual)
        * SO/PO generation at confirmation
        * Price freeze after confirmation
        * Container type inheritance from products
        * Generic allocation tracking infrastructure
        
        State Machine (Refined for Phase 4B):
        ------------------------------------
        * draft → validated (data completeness check only)
        * validated → confirmed (SO/PO creation + confirmation - commitment point)
        * confirmed → partial/allocated (allocation progress)
        * allocated → ready → shipping → delivered → completed
        * Manual closure: action_complete() / action_reopen()
        
        File Organization (NEW):
        -----------------------
        Core Models:
        * dm_deal.py - Model definition, state machine, core logic
        * dm_deal_line.py - Line model definition, core logic
        
        Deal Domain Extensions:
        * dm_deal_workflow.py - Validation, confirmation, allocation management
        * dm_deal_documents.py - SO/PO creation, document generation
        * dm_deal_templates.py - Template selection and application
        
        Allocation Infrastructure:
        -------------------------
        * dm.allocation model (state machine for allocation tracking)
        * allocation_ids (One2many to track all allocations)
        * allocation_status (computed: unallocated/partial/allocated)
        * allocation_count (number of active allocations)
        * action_deallocate_all() (cancel all allocations)
        * action_view_allocations() (view allocation history)
        
        Milestone Infrastructure:
        ------------------------
        * Seven milestone date layers (requested/current/actual):
          - Order Confirmation
          - Production Start
          - Ready to Ship (RTS)
          - Loading
          - Vessel Departure (ETD)
          - Port Arrival (ETA)
          - Final Delivery
        * get_milestone_date() method (single source of truth)
        * CASCADE date management mixin
        
        Extension Pattern:
        -----------------
        dm_production and dm_shipment modules:
        1. Inherit dm.deal model
        2. Add specific fields (production_allocated, production_run_ids, etc.)
        3. Add specific methods (action_allocate_to_production, etc.)
        4. Inherit views to add smart buttons and wizards
        
        Version History:
        ---------------
        v3.0.0: MAJOR REFACTORING
        - Merged dm_deal_state_machine.py into dm_deal.py
        - Added 'partial' and 'completed' states
        - Split dm_deal.py into domain files (workflow, documents, templates)
        - Phase 4B workflow refinement (validation vs confirmation)
        - Token-optimized file sizes (<5000 tokens each)
        - No functional changes - pure organizational refactoring
        
        v2.3.0: Previous major refactor (removed production/shipment specifics)
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