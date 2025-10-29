{
    'name': 'Product Composition and Nutrition',
    'version': '17.0.1.2.0',
    'summary': 'Add composition and nutrition information to products',
    'description': """
Product Composition and Nutrition
==================================

This module extends the product template with composition and nutrition information:

Composition Section:
- Multiple ingredient lines with name and percentage
- Allergens information
- Storage conditions
- Shelf life
- Product of (Country of Origin)
- Halal and Gluten-free flags

Nutrition Facts Section:
- Servings per container and serving size
- Calories
- Complete nutrition facts with absolute values and % daily values:
  - Total Fat (with Saturated and Trans fat)
  - Cholesterol
  - Sodium
  - Total Carbohydrate (with Dietary Fiber, Total Sugars, Added Sugars, Sugar Alcohol)
  - Protein
  - Vitamin D
  - Calcium
  - Iron
  - Potassium

Features:
- Validation to ensure composition percentages don't exceed 100%
- Proper data structure for nutrition facts following FDA guidelines
- Integration with existing product management workflow
    """,
    'category': 'Inventory/Inventory',
    'author': 'Philip Etingen for Donna Mello Distribution Solutions',
    'website': 'https://www.donnamello.com',
    'depends': ['product', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}