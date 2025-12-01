{
    'name': 'DM Deal Management',
    'version': '17.0.6.0.0',
    'category': 'Sales/Sales',
    'summary': 'Deal management with sub-deal architecture for partial shipments',
    'description': """
        DonnaMello Deal Management Module - v6.0 SUB-DEAL ARCHITECTURE
        ==============================================================
        
        PHASE 0: Sub-Deal Architecture (1:1 relationship)
        -------------------------------------------------
        
        New Architecture:
        * dm.deal: Commercial header (customer, PO, terms)
        * dm.deal.subdeal: Execution layer (lines, SO/PO, shipment)
        * 1:1 relationship in Phase 0 (single subdeal per deal)
        * Prepares for 1:N in Phase 1 (deal splitting for backlog)
        
        Key Changes:
        * Deal lines now belong to subdeal (subdeal_id)
        * SO/PO link to both deal and subdeal
        * State aggregated from subdeals
        * Milestones stored on subdeal, aggregated to deal
        * All existing functionality preserved via delegation
        
        Backward Compatibility:
        * deal.line_ids still works (delegated to primary_subdeal)
        * deal.sale_order_id still works (delegated)
        * deal.state still works (computed from subdeal)
        * All views unchanged (delegation is transparent)
        
        Previous Features (Unchanged):
        -------------------------
        * Customer PO# tracking (mandatory)
        * Deal template hierarchy (product → category → generic)
        * Package-native quantities with 6-decimal pricing
        * Three-layer date management (requested/current/actual)
        * SO/PO generation at confirmation
        * Price freeze after confirmation
        * Container type inheritance from products
        * Production status tracking
        * Production lot tracking
        
        File Organization:
        -----------------
        Core Models:
        * dm_deal_subdeal.py - Sub-deal model (NEW)
        * dm_deal.py - Deal model with subdeal relationship
        * dm_deal_line.py - Line model (parent changed to subdeal)
        
        Extensions:
        * dm_deal_workflow.py - Workflow (delegates to subdeal)
        * dm_deal_milestones.py - Milestones (CASCADE logic)
        * dm_deal_documents.py - SO/PO creation (links to subdeal)
        * dm_deal_subdeal_workflow.py - Subdeal workflow (NEW)
        
        Version History:
        ---------------
        v6.0.0: PHASE 0 - SUB-DEAL ARCHITECTURE
        - Added dm.deal.subdeal model
        - Changed dm.deal.line parent to subdeal
        - Added state/milestone aggregation
        - Added SO/PO subdeal linking
        - Preserved all existing functionality
        
        v5.0.0: Production planning and lot tracking
        v4.0.0: Sprint 1-3 cleanup
        v3.0.0: Domain-based file organization
        v2.0.0: Initial allocation system
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'dm_base',
        'dm_master_data',
        'dm_packaging',
        'dm_pricing',
        'dm_capacity_planning',
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
        'views/dm_deal_subdeal_views.xml',
        'views/dm_deal_views.xml',
        'views/dm_deal_line_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        # 'views/account_move_views.xml',
        'wizards/deal_template_selection_wizard.xml',
        'wizards/deal_supplier_selection_wizard_views.xml',
        'wizards/deal_creation_wizard_views.xml',
        'wizards/dm_deal_line_lot_wizard_views.xml',
        'views/dm_deal_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}