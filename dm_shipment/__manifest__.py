{
    'name': 'DM Shipment Management',
    'version': '17.0.1.0.0',
    'category': 'Operations/Inventory',
    'summary': 'Shipment allocation endpoint - Black box implementation',
    'description': """
        DonnaMello Shipment Management - BLACK BOX MODULE
        =================================================
        
        Minimal implementation providing allocation endpoints for shipment workflow.
        
        Core Features:
        --------------
        * Shipment model (allocation target)
        * Deal-to-Shipment allocation
        * Shipment allocation wizard
        * Extends dm_deal with shipment fields
        * Extends dm_allocation with shipment reference
        
        Architecture:
        -------------
        This is a BLACK BOX implementation providing minimal functionality
        for the allocation system. Business logic should be expanded in
        future iterations.
        
        What This Module Does:
        ----------------------
        - Creates shipments as allocation targets
        - Links deals to shipments via dm_allocation
        - Tracks shipment allocation status on deals
        - Provides allocation/deallocation actions
        
        What This Module Does NOT Do (Future Expansion):
        -------------------------------------------------
        - Container optimization/packing
        - Freight forwarder integration
        - Customs documentation
        - Bill of lading generation
        - Shipping cost calculation
        - Track & trace integration
        - Shipment reporting/analytics
        
        Extension Pattern:
        ------------------
        Inherits dm.deal to add:
        - shipment_allocated (Boolean)
        - shipment_ids (Many2many)
        - shipment_count (Integer)
        - action_allocate_to_shipment()
        
        Inherits dm.allocation to add:
        - shipment_id (Many2one)
        
        Version: 1.0.0 (Black Box)
        Status: Minimal Implementation
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'dm_deal',
        'dm_master_data',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/dm_shipment_views.xml',
        'views/dm_deal_shipment_views.xml',
        'views/dm_production_run_shipment_views.xml',
        'wizards/shipment_allocation_wizard_views.xml',
        'data/shipment_server_actions.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}