# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class DealCreationWizardLine(models.TransientModel):
    _name = 'dm.deal.creation.wizard.line'
    _description = 'Deal Creation Wizard Line'
    _order = 'sequence, id'
    
    wizard_id = fields.Many2one(
        'dm.deal.creation.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    sequence = fields.Integer(string='Sequence', default=10)

    customer_product_code = fields.Char(
        string='Customer Code',
        help='Search by customer product code'
    )
    
    # Product selection
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('sale_ok', '=', True)]
    )
    
    packaging_id = fields.Many2one(
        'product.packaging',
        string='Packaging',
        required=True,
        domain="[('product_id', '=', product_id)]"
    )
    
    # Entry mode
    entry_mode = fields.Selection([
        ('pkg', 'By Package'),
        ('kg', 'By Weight (kg)')
    ], string='Entry Mode', default='pkg', required=True)
    
    # Quantity fields
    quantity_packaging = fields.Float(
        string='Qty (Packages)',
        digits=(16, 3)
    )
    
    weight = fields.Float(
        string='Weight (kg)',
        digits=(16, 3),
        help='Enter weight in kg mode, or displays calculated weight in package mode'
    )
    
    # Pricing
    price_packaging_sale = fields.Float(
        string='Price/Package',
        digits=(16, 6),
        required=True
    )

    price_per_kg_reference = fields.Float(
        string='Price/kg',
        compute='_compute_price_per_kg_reference',
        digits=(16, 3),
        help='Price per kilogram (from customer pricelist or computed)'
    )

    amount_sale = fields.Monetary(
        string='Total',
        compute='_compute_amount_sale',
        currency_field='currency_id'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='wizard_id.currency_id'
    )
    
    # Product info (for display)
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        compute='_compute_supplier_id',
        store=False,
        help='Primary supplier for this product'
    )

    @api.depends('product_id')
    def _compute_supplier_id(self):
        """Get primary supplier from product's vendor list"""
        for line in self:
            supplier = False
            if line.product_id:
                # Get first supplier from product.supplierinfo (ordered by sequence)
                supplier_info = self.env['product.supplierinfo'].search([
                    '|',
                    ('product_id', '=', line.product_id.id),
                    '&',
                    ('product_id', '=', False),
                    ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id),
                ], limit=1, order='sequence, id')
                
                if supplier_info:
                    supplier = supplier_info.partner_id
            
            line.supplier_id = supplier
    
    product_moq = fields.Float(
        string='MOQ',
        help="Minimum Order Quantity from customer pricelist"
    )
    
    moq_status = fields.Selection([
        ('ok', 'OK'),
        ('below', 'Below MOQ'),
        ('unknown', 'Unknown')
    ], compute='_compute_moq_status', string='MOQ Status')
    
    moq_override_reason = fields.Char(
        string='MOQ Override Reason',
        help="Reason for ordering below MOQ"
    )
    
    # ===== COMPUTED FIELDS =====

    @api.depends('price_packaging_sale', 'packaging_id', 'product_id.weight')
    def _compute_price_per_kg_reference(self):
        """Compute price per kg for display"""
        for line in self:
            if not line.packaging_id or not line.price_packaging_sale:
                line.price_per_kg_reference = 0.0
                continue
            
            # Get total weight of package
            if hasattr(line.packaging_id, 'packaging_net_weight'):
                total_weight = line.packaging_id.packaging_net_weight or 0
            else:
                total_weight = (line.packaging_id.qty or 0) * (line.product_id.weight or 0)
            
            if total_weight > 0:
                line.price_per_kg_reference = line.price_packaging_sale / total_weight
            else:
                line.price_per_kg_reference = 0.0
    
    @api.onchange('quantity_packaging', 'packaging_id', 'product_id')
    def _onchange_quantity_packaging_calculate_weight(self):
        """Calculate weight when entering by packages"""
        if self.entry_mode == 'pkg' and self.quantity_packaging and self.quantity_packaging > 0:
            if self.packaging_id and self.product_id and self.product_id.weight:
                package_weight = self.packaging_id.qty * self.product_id.weight
                if package_weight > 0:
                    self.weight = self.quantity_packaging * package_weight
    
    @api.depends('quantity_packaging', 'price_packaging_sale')
    def _compute_amount_sale(self):
        """Compute line total"""
        for line in self:
            line.amount_sale = line.quantity_packaging * line.price_packaging_sale
    
    @api.depends('quantity_packaging', 'product_moq')
    def _compute_moq_status(self):
        """Check MOQ status"""
        for line in self:
            if not line.product_moq or line.product_moq == 0:
                line.moq_status = 'unknown'
            elif line.quantity_packaging >= line.product_moq:
                line.moq_status = 'ok'
            else:
                line.moq_status = 'below'
    
    # ===== ONCHANGE METHODS (Now delegate to model) =====
    
    @api.onchange('customer_product_code')
    def _onchange_customer_product_code(self):
        """Look up product by customer code - delegates to model"""
        if not self.customer_product_code or not self.wizard_id.customer_id:
            return
        
        # Use model method
        result = self.env['dm.deal.line'].lookup_product_by_customer_code(
            self.wizard_id.customer_id.id,
            self.customer_product_code
        )
        
        if result:
            self.product_id = result['product_id']
            self.packaging_id = result['product_packaging_id']
            self.price_packaging_sale = result['package_price']
            self.product_moq = result.get('moq_packages', 0)
            
            _logger.info(
                f"Found product by customer code '{self.customer_product_code}': "
                f"Product ID {result['product_id']}"
            )
        else:
            return {
                'warning': {
                    'title': _('Code Not Found'),
                    'message': _(
                        'Customer code "%s" not found for %s.'
                    ) % (self.customer_product_code, self.wizard_id.customer_id.name)
                }
            }

    @api.onchange('product_id', 'packaging_id')
    def _onchange_product_load_data(self):
        """Load pricing when product/packaging selected - delegates to model"""
        if not self.product_id or not self.packaging_id or not self.wizard_id.customer_id:
            return
        
        # Use model method
        result = self.env['dm.deal.line'].fetch_customer_price_for_wizard(
            self.wizard_id.customer_id.id,
            self.product_id.id,
            self.packaging_id.id
        )
        
        if result:
            self.price_packaging_sale = result['package_price']
            self.product_moq = result.get('moq_packages', 0)
            
            if result.get('customer_product_code') and not self.customer_product_code:
                self.customer_product_code = result['customer_product_code']
            
            _logger.info(
                f"Fetched customer price: {self.price_packaging_sale} "
                f"for product {self.product_id.id} / packaging {self.packaging_id.id}"
            )
        else:
            _logger.warning(
                f"No customer price found for customer {self.wizard_id.customer_id.id} / "
                f"product {self.product_id.id} / packaging {self.packaging_id.id}"
            )

    @api.onchange('product_id')
    def _onchange_product_check_supplier(self):
        """Warn if product has different supplier than existing lines"""
        if not self.product_id or not self.wizard_id:
            return
        
        # Get this product's supplier
        supplier_info = self.env['product.supplierinfo'].search([
            '|',
            ('product_id', '=', self.product_id.id),
            '&',
            ('product_id', '=', False),
            ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
        ], limit=1, order='sequence, id')
        
        if not supplier_info:
            return  # No supplier - will be caught by other validation
        
        new_supplier = supplier_info.partner_id
        
        # Check existing lines for different supplier
        for line in self.wizard_id.line_ids:
            if line.id == self.id or not line.product_id:
                continue
            
            # Get existing line's supplier
            existing_supplier_info = self.env['product.supplierinfo'].search([
                '|',
                ('product_id', '=', line.product_id.id),
                '&',
                ('product_id', '=', False),
                ('product_tmpl_id', '=', line.product_id.product_tmpl_id.id),
            ], limit=1, order='sequence, id')
            
            if existing_supplier_info and existing_supplier_info.partner_id != new_supplier:
                return {
                    'warning': {
                        'title': _('Multiple Suppliers Not Allowed'),
                        'message': _(
                            'Product "%s" has supplier "%s", but other lines use supplier "%s".\n\n'
                            'A deal can only have products from a single supplier.\n\n'
                            'Please either:\n'
                            '• Select a different product from "%s"\n'
                            '• Create a separate deal for this product'
                        ) % (
                            self.product_id.name,
                            new_supplier.name,
                            existing_supplier_info.partner_id.name,
                            existing_supplier_info.partner_id.name
                        )
                    }
                }
    
    @api.onchange('weight', 'packaging_id', 'product_id')
    def _onchange_weight(self):
        """Convert kg to packages when entering by weight"""
        if self.entry_mode == 'kg' and self.weight > 0:
            if not self.product_id:
                return {
                    'warning': {
                        'title': _('Product Required'),
                        'message': _('Please select a product first.')
                    }
                }
            
            if not self.packaging_id:
                return {
                    'warning': {
                        'title': _('Packaging Required'),
                        'message': _('Please select packaging first.')
                    }
                }
            
            if not self.product_id.weight or self.product_id.weight == 0:
                return {
                    'warning': {
                        'title': _('Weight Not Defined'),
                        'message': _(
                            'Product %s has no weight defined. '
                            'Please update product master data or switch to package entry mode.'
                        ) % self.product_id.name
                    }
                }
            
            # Calculate package weight
            package_weight = self.packaging_id.qty * self.product_id.weight
            
            if package_weight == 0:
                return {
                    'warning': {
                        'title': _('Invalid Weight'),
                        'message': _('Package weight calculates to zero. Check product and packaging configuration.')
                    }
                }
            
            # Calculate packages from weight
            calculated_packages = self.weight / package_weight
            
            # Check if divisible evenly (tolerance for float precision)
            if abs(calculated_packages - round(calculated_packages)) > 0.001:
                packages_floor = int(calculated_packages)
                packages_ceil = packages_floor + 1
                weight_floor = packages_floor * package_weight
                weight_ceil = packages_ceil * package_weight
                
                return {
                    'warning': {
                        'title': _('Weight Does Not Divide Evenly'),
                        'message': _(
                            'Weight %.3f kg does not divide evenly into packages.\n'
                            'Each package weighs %.3f kg.\n'
                            'Result would be %.3f packages (fractional not allowed).\n\n'
                            'Suggestions:\n'
                            '• %d packages = %.3f kg\n'
                            '• %d packages = %.3f kg\n\n'
                            'Please adjust weight or switch to package entry mode.'
                        ) % (
                            self.weight,
                            package_weight,
                            calculated_packages,
                            packages_floor, weight_floor,
                            packages_ceil, weight_ceil
                        )
                    }
                }
            
            # Set package quantity
            self.quantity_packaging = round(calculated_packages)
    
    # ===== CONSTRAINTS =====
    
    @api.constrains('quantity_packaging')
    def _check_quantity_positive(self):
        """Ensure quantity is positive"""
        for line in self:
            if line.quantity_packaging <= 0:
                raise ValidationError(_(
                    'Quantity must be greater than zero for product: %s'
                ) % line.product_id.name)
    
    @api.constrains('price_packaging_sale')
    def _check_price_positive(self):
        """Ensure price is positive"""
        for line in self:
            if line.price_packaging_sale < 0:
                raise ValidationError(_(
                    'Price cannot be negative for product: %s'
                ) % line.product_id.name)