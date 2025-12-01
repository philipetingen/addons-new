# -*- coding: utf-8 -*-
{
    'name': 'DM Shipment Management',
    'version': '2.1.0',  # Sprint 3
    'category': 'Sales',
    'summary': 'Container-centric shipment management for DonnaMello',
    'description': """
        Shipment Management v2.1 - Sprint 3: Loading Workflow
        ======================================================
        
        Sprint 3: Loading Confirmation
        - Capture actual loaded quantities per container line
        - Lot-level allocation tracking
        - VGM declaration per container
        - Variance analysis (planned vs loaded)
        - Deal state progression on loading complete
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'dm_base',
        'dm_master_data',
        'dm_deal',
    ],
    'data': [
        'security/dm_shipment_security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/shipment_views.xml',
        'views/container_views.xml',
        'views/deal_allocation_views.xml',
        'views/dm_deal_views_extension.xml',
        'wizards/shipment_allocation_wizard_views.xml',
        'wizards/container_allocation_wizard_views.xml',
        'wizards/loading_confirmation_wizard_views.xml',
        'wizards/loading_lot_wizard_views.xml',
        'wizards/shipment_reschedule_wizard_views.xml',
        'views/shipment_menu.xml',    
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}