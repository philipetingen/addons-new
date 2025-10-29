from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Composition fields
    composition_ids = fields.One2many('product.composition', 'product_tmpl_id', string='Composition')
    total_composition_percentage = fields.Float(string='Total %', compute='_compute_total_composition_percentage', store=False)
    allergens = fields.Text(string='Allergens')
    storage_conditions = fields.Text(string='Storage Conditions')
    shelf_life = fields.Char(string='Shelf Life')
    is_halal = fields.Boolean(string='Halal', default=False)
    is_kosher = fields.Boolean(string='Kosher', default=False)
    is_gluten_free = fields.Boolean(string='Gluten-Free', default=False)
    
    # Nutrition Facts fields
    servings_per_container = fields.Char(string='Servings Per Container')
    serving_size = fields.Char(string='Serving Size')
    calories = fields.Float(string='Calories', digits=(12, 2))
    
    # Nutrition facts lines
    nutrition_fact_ids = fields.One2many('product.nutrition.fact', 'product_tmpl_id', string='Nutrition Facts')
    
    @api.depends('composition_ids.percentage')
    def _compute_total_composition_percentage(self):
        for record in self:
            record.total_composition_percentage = sum(comp.percentage for comp in record.composition_ids)
    
    @api.constrains('composition_ids')
    def _check_composition_percentage(self):
        for record in self:
            if record.composition_ids:
                total_percentage = sum(comp.percentage for comp in record.composition_ids)
                if total_percentage != 100 and total_percentage > 0:
                    raise ValidationError("Total percentage of all composition elements must equal 100%")

    @api.model
    def create(self, vals):
        product = super(ProductTemplate, self).create(vals)
        product._create_default_nutrition_facts()
        return product

    def _create_default_nutrition_facts(self):
        """Create default nutrition fact lines"""
        default_nutrition_facts = [
            {'name': 'Total Fat', 'unit': 'g', 'sequence': 10},
            {'name': 'Saturated Fat', 'unit': 'g', 'sequence': 11},
            {'name': 'Trans Fat', 'unit': 'g', 'sequence': 12},
            {'name': 'Cholesterol', 'unit': 'mg', 'sequence': 20},
            {'name': 'Sodium', 'unit': 'mg', 'sequence': 30},
            {'name': 'Total Carbohydrate', 'unit': 'g', 'sequence': 40},
            {'name': 'Dietary Fiber', 'unit': 'g', 'sequence': 41},
            {'name': 'Total Sugars', 'unit': 'g', 'sequence': 42},
            {'name': 'Includes Added Sugars', 'unit': 'g', 'sequence': 43},
            {'name': 'Sugar Alcohol', 'unit': 'g', 'sequence': 44},
            {'name': 'Protein', 'unit': 'g', 'sequence': 50},
            {'name': 'Vitamin D', 'unit': 'mcg', 'sequence': 60},
            {'name': 'Calcium', 'unit': 'mg', 'sequence': 70},
            {'name': 'Iron', 'unit': 'mg', 'sequence': 80},
            {'name': 'Potassium', 'unit': 'mg', 'sequence': 90},
        ]
        
        nutrition_facts_to_create = []
        for fact in default_nutrition_facts:
            nutrition_facts_to_create.append({
                'product_tmpl_id': self.id,
                'nutrition_fact_name': fact['name'],
                'unit': fact['unit'],
                'sequence': fact['sequence'],
                'absolute_value': 0.0,
                'daily_value_percent': 0.0,
            })
        
        self.env['product.nutrition.fact'].create(nutrition_facts_to_create)


class ProductComposition(models.Model):
    _name = 'product.composition'
    _description = 'Product Composition'
    _order = 'sequence, id'
    
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    ingredient_name = fields.Char(string='Ingredient Name', required=True)
    percentage = fields.Float(string='Percentage (%)', digits=(5, 2), required=True)
    
    @api.constrains('percentage')
    def _check_percentage_range(self):
        for record in self:
            if record.percentage < 0 or record.percentage > 100:
                raise ValidationError("Percentage must be between 0 and 100")


class ProductNutritionFact(models.Model):
    _name = 'product.nutrition.fact'
    _description = 'Product Nutrition Fact'
    _order = 'sequence, id'
    
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    nutrition_fact_name = fields.Char(string='Nutrition Fact Name', required=True)
    absolute_value = fields.Float(string='Absolute Value', digits=(12, 2))
    unit = fields.Selection([
        ('g', 'g'),
        ('mg', 'mg'),
        ('mcg', 'mcg'),
    ], string='Unit', default='g')
    daily_value_percent = fields.Float(string='% DV', digits=(12, 1))
    
    @api.constrains('daily_value_percent')
    def _check_daily_value_percent(self):
        for record in self:
            if record.daily_value_percent < 0:
                raise ValidationError("Daily value percentage cannot be negative")