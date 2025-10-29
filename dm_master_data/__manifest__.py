{
    'name': 'DM Master Data',
    'version': '17.0.1.1.0',  # Minor version bump for new features
    'summary': 'Master data management for Donna Mello Distribution Solutions with enhanced packaging',
    'description': """
        Master Data Management Module
        ==============================
        
        This module manages all master data for the DonnaMello Distribution System including:
        
        Product Enhancements:
        * DM-specific product attributes (TI/HI, consumer weight, branding)
        * Collections, colors, shapes, textures, and other characteristics
        * Hierarchical packaging with standard types
        * Package-in-package capability
        * Container shipping preferences
        * Temperature and humidity requirements
        
        Packaging Features:
        * Standard packaging types (Unit/Inner/Carton/Pallet/Container)
        * Hierarchical package relationships
        * Automatic UoM creation for packages
        * Smart volume and weight calculations
        * Package-native pricing support
        
        Logistics:
        * Port management
        * Container types
        * Document types
        * QC check types
        
        Compliance:
        * Compliance regions (required field)
        * Product compatibility rules
        
        Version 17.0.1.1.0 Changes:
        --------------------------
        * Added hierarchical packaging system
        * Added standard packaging types
        * Added missing DM product fields (TI/HI, consumer weight, branding)
        * Enhanced package calculations
        * Split color fields into inner and coating
        * Made compliance regions required
        
        This module must be installed after dm_base.
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'category': 'Inventory',
    'depends': [
        'dm_base',
        'dm_packaging',
        'product',
        'sale',
        'purchase',
        'stock',
        'uom',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        
        # Data files
        'data/dm_container_types.xml',
        'data/dm_document_types.xml',
        'data/dm_qc_types.xml',
        'data/dm_ports.xml',
        'data/dm_product_data.xml',
        'data/dm_milestone_types.xml', 
        
        # Views
        'views/dm_container_type_views.xml',
        'views/dm_document_type_views.xml',
        'views/dm_port_views.xml',
        'views/dm_qc_type_views.xml',
        'views/dm_product_config_views.xml',
        'views/product_views.xml',  # UPDATED
        'views/dm_milestone_type_views.xml',
        'views/dm_master_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}