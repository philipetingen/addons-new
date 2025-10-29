# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

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
        related='product_id.seller_ids.partner_id',
        string='Supplier',
        store=False
    )
    
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
                # Calculate package weight
                package_weight = self.packaging_id.qty * self.product_id.weight
                if package_weight > 0:
                    self.weight = self.quantity_packaging * package_weight
                    _logger.info(f"Calculated weight: {self.weight} kg from {self.quantity_packaging} packages")
    
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
    
    # ===== ONCHANGE METHODS =====
    
    @api.onchange('customer_product_code')
    def _onchange_customer_product_code(self):
        """Look up product by customer code - REUSED FROM dm_deal_line"""
        if not self.customer_product_code or not self.wizard_id.customer_id:
            return
        
        try:
            # Search in dm.customer.pricelist (same as deal line)
            pricelist_item = self.env['dm.customer.pricelist'].search([
                ('partner_id', '=', self.wizard_id.customer_id.id),
                ('customer_product_code', '=', self.customer_product_code),
                ('active', '=', True),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ], limit=1)
            
            if pricelist_item:
                # Auto-populate product and packaging
                self.product_id = pricelist_item.product_id
                self.packaging_id = pricelist_item.product_packaging_id
                self.price_packaging_sale = pricelist_item.package_price
                self.product_moq = pricelist_item.moq_packages
                
                _logger.info(
                    f"Found product by customer code '{self.customer_product_code}': "
                    f"{pricelist_item.product_id.name}"
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
        
        except Exception as e:
            _logger.error(f"Error looking up customer product code: {str(e)}")

    @api.onchange('product_id', 'packaging_id')
    def _onchange_product_load_data(self):
        """Load pricing when product/packaging selected - REUSED FROM dm_deal_line"""
        if not self.product_id or not self.packaging_id or not self.wizard_id.customer_id:
            return
        
        # Fetch customer price using same method as deal line
        self._fetch_customer_price()

    def _fetch_customer_price(self):
        """
        Fetch customer price from dm.customer.pricelist.
        COPIED FROM dm_deal_line for consistency.
        """
        if not self.product_id or not self.packaging_id or not self.wizard_id.customer_id:
            return
        
        try:
            # Search dm.customer.pricelist
            pricelist_item = self.env['dm.customer.pricelist'].search([
                ('partner_id', '=', self.wizard_id.customer_id.id),
                ('product_id', '=', self.product_id.id),
                ('product_packaging_id', '=', self.packaging_id.id),
                ('active', '=', True),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ], limit=1)
            
            if pricelist_item:
                self.price_packaging_sale = pricelist_item.package_price
                self.product_moq = pricelist_item.moq_packages
                
                # Auto-fill customer code if not already set
                if pricelist_item.customer_product_code and not self.customer_product_code:
                    self.customer_product_code = pricelist_item.customer_product_code
                
                _logger.info(
                    f"Fetched customer price: {self.price_packaging_sale} "
                    f"for {self.product_id.name} ({self.packaging_id.name})"
                )
            else:
                _logger.warning(
                    f"No customer price found for {self.wizard_id.customer_id.name} / "
                    f"{self.product_id.name} / {self.packaging_id.name}"
                )
        
        except Exception as e:
            _logger.error(f"Error fetching customer price: {str(e)}", exc_info=True)
    
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
                # Calculate suggestions
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
                            'â€¢ %d packages = %.3f kg\n'
                            'â€¢ %d packages = %.3f kg\n\n'
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
            
            # Set package quantity (rounded to handle float precision)
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