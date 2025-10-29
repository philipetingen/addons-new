# __manifest__.py
{
    'name': 'DM Packaging Infrastructure',
    'version': '17.0.1.0.0',
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': ['dm_base', 'product', 'uom'],
    'data': [
        'security/ir.model.access.csv',
        'data/packaging_standard_types.xml',
        'views/packaging_standard_type_views.xml',
        'views/product_packaging_views.xml',
        'views/dm_packaging_menu.xml',
    ],
}