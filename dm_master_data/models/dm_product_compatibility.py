from odoo import models, fields, api
from odoo.exceptions import UserError


class DmProductCompatibility(models.Model):
    """
    Product compatibility rules for container optimization.
    Per Appendix Section 1.2: Product Compatibility Matrix
    """
    _name = 'dm.product.compatibility'
    _description = 'Product Compatibility Rules'
    _rec_name = 'display_name'
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        ondelete='cascade'
    )
    
    incompatible_product_ids = fields.Many2many(
        'product.product',
        'dm_product_incompatibility_detail_rel',
        'compatibility_id',
        'incompatible_id',
        string='Incompatible Products',
        help='Products that cannot be shipped together'
    )
    
    incompatibility_type = fields.Selection([
        ('temperature', 'Different Temperature Requirements'),
        ('chemical', 'Chemical Incompatibility'),
        ('contamination', 'Cross-Contamination Risk'),
        ('regulatory', 'Regulatory Restriction'),
        ('customer', 'Customer Requirement'),
        ('odor', 'Odor Transfer Risk'),
        ('physical', 'Physical Incompatibility')
    ], string='Incompatibility Type', required=True, default='contamination')
    
    reason = fields.Text(
        string='Reason',
        help='Detailed reason for incompatibility'
    )
    
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    @api.depends('product_id', 'incompatibility_type')
    def _compute_display_name(self):
        """Compute display name."""
        for record in self:
            if record.product_id:
                type_label = dict(self._fields['incompatibility_type'].selection).get(
                    record.incompatibility_type, ''
                )
                record.display_name = f"{record.product_id.name} - {type_label}"
            else:
                record.display_name = 'New Compatibility Rule'
    
    @api.model
    def check_container_compatibility(self, product_ids):
        """
        Check if products can be shipped together.
        
        Args:
            product_ids: List of product IDs to check
            
        Returns:
            dict: Compatibility check results
        """
        if len(product_ids) < 2:
            return {'compatible': True, 'issues': []}
        
        products = self.env['product.product'].browse(product_ids)
        issues = []
        
        # Check each pair of products
        for i, product1 in enumerate(products):
            for product2 in products[i+1:]:
                # Check direct incompatibility
                if product2 in product1.incompatible_product_ids:
                    issues.append({
                        'product1': product1.name,
                        'product2': product2.name,
                        'type': 'direct',
                        'reason': 'Products marked as incompatible'
                    })
                
                # Check temperature compatibility
                if product1.requires_refrigeration != product2.requires_refrigeration:
                    issues.append({
                        'product1': product1.name,
                        'product2': product2.name,
                        'type': 'temperature',
                        'reason': 'Different refrigeration requirements'
                    })
                elif product1.requires_refrigeration and product2.requires_refrigeration:
                    # Both need refrigeration - check temperature ranges
                    min_temp = max(product1.min_temperature or -30, 
                                  product2.min_temperature or -30)
                    max_temp = min(product1.max_temperature or 30,
                                  product2.max_temperature or 30)
                    
                    if min_temp > max_temp:
                        issues.append({
                            'product1': product1.name,
                            'product2': product2.name,
                            'type': 'temperature',
                            'reason': f'Incompatible temperature ranges'
                        })
        
        return {
            'compatible': len(issues) == 0,
            'issues': issues
        }
    
    def validate_temperature_requirements(self, products, container_type):
        """
        Validate temperature requirements for container.
        Per Appendix Section 1.3: Temperature Zone Management
        
        Args:
            products: Product recordset
            container_type: Container type record
            
        Returns:
            dict: Temperature validation results
        """
        reefer_products = products.filtered('requires_refrigeration')
        
        if not reefer_products:
            return {
                'valid': True,
                'requires_reefer': False,
                'temperature_range': None
            }
        
        if not container_type.is_reefer:
            return {
                'valid': False,
                'requires_reefer': True,
                'error': 'Products require refrigerated container'
            }
        
        # Calculate compatible temperature range
        min_temps = reefer_products.mapped('min_temperature')
        max_temps = reefer_products.mapped('max_temperature')
        
        min_temp = max(filter(None, min_temps)) if min_temps else -30
        max_temp = min(filter(None, max_temps)) if max_temps else 30
        
        if min_temp > max_temp:
            return {
                'valid': False,
                'requires_reefer': True,
                'error': f'Incompatible temperature requirements: {min_temp}°C to {max_temp}°C'
            }
        
        # Set optimal temperature (middle of range)
        optimal_temp = (min_temp + max_temp) / 2
        
        return {
            'valid': True,
            'requires_reefer': True,
            'temperature_range': {
                'min': min_temp,
                'max': max_temp,
                'optimal': optimal_temp
            }
        }
    
    @api.model
    def create_incompatibility(self, product1_id, product2_id, type_='contamination', reason=''):
        """
        Create bidirectional incompatibility between products.
        
        Args:
            product1_id: First product ID
            product2_id: Second product ID
            type_: Incompatibility type
            reason: Reason for incompatibility
        """
        product1 = self.env['product.product'].browse(product1_id)
        product2 = self.env['product.product'].browse(product2_id)
        
        # Add to both products
        product1.incompatible_product_ids = [(4, product2_id)]
        product2.incompatible_product_ids = [(4, product1_id)]
        
        # Create compatibility record
        self.create({
            'product_id': product1_id,
            'incompatible_product_ids': [(4, product2_id)],
            'incompatibility_type': type_,
            'reason': reason or f'{product1.name} incompatible with {product2.name}'
        })
        
        return True