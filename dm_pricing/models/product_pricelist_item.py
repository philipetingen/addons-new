# -*- coding: utf-8 -*-
"""
Extend standard Odoo pricelist items with package-based pricing.
Maintains 6-decimal precision and package-native operations.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProductPricelistItem(models.Model):
    """
    Extend standard pricelist item with DonnaMello package pricing.
    
    CRITICAL: This allows us to use Odoo's standard pricelist mechanism
    while maintaining our 6-decimal package-native precision.
    """
    _inherit = 'product.pricelist.item'
    
    # ==========================================
    # PACKAGE-BASED PRICING (DM EXTENSION)
    # ==========================================
    
    dm_is_package_price = fields.Boolean(
        string='Package-Based Pricing',
        default=False,
        help='Enable DonnaMello package-based pricing with 6-decimal precision'
    )
    
    dm_packaging_id = fields.Many2one(
        'product.packaging',
        string='Package Type',
        help='Specific packaging for this price'
    )
    
    dm_package_price = fields.Float(
        string='Price per Package',
        digits=(16, 6),
        help='Package price with 6-decimal precision'
    )
    
    dm_unit_price_computed = fields.Float(
        string='Computed Unit Price',
        compute='_compute_dm_unit_price',
        store=True,
        digits=(16, 6),
        help='Unit price calculated from package price (for reference)'
    )
    
    dm_price_per_kg = fields.Float(
        string='Price per kg',
        compute='_compute_dm_price_per_kg',
        store=True,
        digits=(16, 3),
        help='Price per kilogram'
    )
    
    # ==========================================
    # MOQ MANAGEMENT (DM EXTENSION)
    # ==========================================
    
    dm_moq_packages = fields.Float(
        string='MOQ (Packages)',
        digits=(16, 3),
        default=1.0,
        help='Minimum order quantity in packages'
    )
    
    dm_moq_enforcement = fields.Selection([
        ('none', 'No Enforcement'),
        ('warning', 'Warning Only'),
        ('strict', 'Block Order'),
        ('approval', 'Requires Approval')
    ], string='MOQ Enforcement', default='warning')
    
    # ==========================================
    # CUSTOMER/VENDOR CODES (DM EXTENSION)
    # ==========================================
    
    dm_customer_product_code = fields.Char(
        string='Customer Product Code',
        help='Product code used by the customer'
    )
    
    dm_customer_description = fields.Text(
        string='Customer Description',
        help='Product description in customer terminology'
    )
    
    # ==========================================
    # BILATERAL SYNC TRACKING
    # ==========================================
    
    dm_customer_pricelist_id = fields.Many2one(
        'dm.customer.pricelist',
        string='DM Customer Price Record',
        readonly=True,
        help='Link to DM customer pricelist record (for bilateral sync)'
    )
    
    # ==========================================
    # COMPUTED METHODS
    # ==========================================
    
    @api.depends('dm_package_price', 'dm_packaging_id', 'dm_packaging_id.qty')
    def _compute_dm_unit_price(self):
        """Calculate unit price from package price"""
        for item in self:
            if item.dm_is_package_price and item.dm_packaging_id and item.dm_packaging_id.qty:
                item.dm_unit_price_computed = item.dm_package_price / item.dm_packaging_id.qty
            else:
                item.dm_unit_price_computed = 0.0
    
    @api.depends('dm_package_price', 'dm_packaging_id', 'product_tmpl_id.weight')
    def _compute_dm_price_per_kg(self):
        """Calculate price per kg from package price"""
        for item in self:
            if not item.dm_is_package_price or not item.dm_packaging_id:
                item.dm_price_per_kg = 0.0
                continue
            
            # Get total weight of package
            if hasattr(item.dm_packaging_id, 'packaging_net_weight'):
                total_weight = item.dm_packaging_id.packaging_net_weight or 0
            else:
                # Fallback: units × product weight
                total_weight = (item.dm_packaging_id.qty or 0) * (item.product_tmpl_id.weight or 0)
            
            if total_weight > 0:
                item.dm_price_per_kg = item.dm_package_price / total_weight
            else:
                item.dm_price_per_kg = 0.0
    
    # ==========================================
    # OVERRIDE ODOO'S PRICE COMPUTATION
    # ==========================================
    
    def _compute_price(self, product, quantity, uom, date=False, currency=None):
        """
        Override Odoo's price computation to use DM package pricing.
        
        CRITICAL: This makes Odoo respect our 6-decimal package prices
        throughout SO/PO/Invoice generation.
        """
        self.ensure_one()
        
        # Use DM package pricing if enabled
        if self.dm_is_package_price and self.dm_packaging_id:
            # Check if requested UoM matches our packaging UoM
            packaging_uom = self.dm_packaging_id.uom_id if hasattr(self.dm_packaging_id, 'uom_id') else self.dm_packaging_id.product_uom_id
            
            if uom == packaging_uom:
                # Direct package price (no conversion needed)
                price = self.dm_package_price
            else:
                # Need to convert to requested UoM
                # Use computed unit price and convert
                price = self.dm_unit_price_computed
                if uom and product.uom_id != uom:
                    price = product.uom_id._compute_price(price, uom)
            
            _logger.debug(
                f"DM Package Price: {self.dm_package_price} for {self.dm_packaging_id.name}, "
                f"computed price: {price} for UoM {uom.name}"
            )
            
            return price
        
        # Fallback to standard Odoo pricing
        return super()._compute_price(product, quantity, uom, date, currency)
    
    # ==========================================
    # CONSTRAINTS
    # ==========================================
    
    @api.constrains('dm_is_package_price', 'dm_packaging_id', 'dm_package_price')
    def _check_package_pricing(self):
        """Validate package pricing configuration"""
        for item in self:
            if item.dm_is_package_price:
                if not item.dm_packaging_id:
                    raise ValidationError(_("Package type is required for package-based pricing"))
                if item.dm_package_price <= 0:
                    raise ValidationError(_("Package price must be positive"))
    
    _sql_constraints = [
        ('dm_positive_package_price', 
         'CHECK(NOT dm_is_package_price OR dm_package_price > 0)', 
         'Package price must be positive!'),
        ('dm_positive_moq', 
         'CHECK(dm_moq_packages > 0)', 
         'MOQ must be positive!'),
    ]