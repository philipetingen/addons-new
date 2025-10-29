{
    'name': 'DonnaMello Pricing',
    'version': '17.0.2.0.0',  # Incremented for major changes
    'category': 'Sales',
    'summary': 'Package-based pricing with Odoo pricelist integration',
    'description': """
DonnaMello Pricing Module
=========================

Extends Odoo's standard pricelists with:
- 6-decimal precision package-based pricing
- Bilateral sync between quick-entry and standard pricelists
- MOQ management
- Customer/vendor product codes
- Currency-aware pricing

Architecture:
- dm.customer.pricelist: Quick-entry interface
- product.pricelist.item: Extended with DM fields
- Automatic synchronization maintained
    """,
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': [
        'product',
        'sale',
        'purchase',
        'dm_base',           # For CASCADE mixins if needed
        'dm_master_data',    # For port references in vendor prices
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/dm_pricing_menu.xml',
        'views/product_template_views.xml',  # Add pricing tabs
        'views/product_pricelist_item_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}