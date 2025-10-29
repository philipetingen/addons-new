# -*- coding: utf-8 -*-
"""
Extend standard Odoo supplier info with package-based pricing.
This replaces the need for dm.vendor.pricelist model.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProductSupplierinfo(models.Model):
    """
    Extend standard supplier info with DM package pricing.
    
    ARCHITECTURE:
    - Uses Odoo's standard product.supplierinfo model
    - Extends with 6-decimal package pricing
    - No separate dm.vendor.pricelist needed
    - Maintains compatibility with standard Odoo purchasing
    """
    _inherit = 'product.supplierinfo'
    
    # ==========================================
    # PACKAGE-BASED PRICING (DM EXTENSION)
    # ==========================================
    
    dm_is_package_price = fields.Boolean(
        string='Package-Based Pricing',
        default=False,
        help='Enable DonnaMello package-based pricing'
    )
    
    dm_packaging_id = fields.Many2one(
        'product.packaging',
        string='Package Type',
        help='Specific packaging for this vendor price'
    )
    
    dm_package_price = fields.Float(
        string='Price per Package',
        digits=(16, 6),
        help='Vendor price per package with 6-decimal precision'
    )
    
    dm_unit_price_computed = fields.Float(
        string='Computed Unit Price',
        compute='_compute_dm_unit_price',
        store=True,
        digits=(16, 6),
        help='Unit price calculated from package price'
    )
    
    dm_price_per_kg = fields.Float(
        string='Price per kg',
        compute='_compute_dm_price_per_kg',
        store=True,
        digits=(16, 3)
    )
    
    # ==========================================
    # VENDOR-SPECIFIC CODES
    # ==========================================
    
    dm_vendor_product_code = fields.Char(
        string='Vendor Product Code',
        help='Product code used by the vendor'
    )
    
    dm_vendor_description = fields.Text(
        string='Vendor Description'
    )
    
    # ==========================================
    # LOGISTICS & CAPACITY
    # ==========================================
    
    dm_loading_port_id = fields.Many2one(
        'dm.port',
        string='Loading Port',
        help='Default loading port for this vendor-product'
    )
    
    dm_factory_location = fields.Char(
        string='Factory Location'
    )
    
    dm_production_lead_time = fields.Integer(
        string='Production Lead Time (days)',
        help='Days needed for production'
    )
    
    dm_monthly_capacity_packages = fields.Float(
        string='Monthly Capacity (Packages)',
        digits=(16, 3),
        help='Maximum monthly production capacity'
    )
    
    dm_preferred_vendor = fields.Boolean(
        string='Preferred Vendor',
        default=False,
        help='Mark as preferred vendor for this product'
    )
    
    # ==========================================
    # COMPUTED METHODS
    # ==========================================
    
    @api.depends('dm_package_price', 'dm_packaging_id', 'dm_packaging_id.qty')
    def _compute_dm_unit_price(self):
        """Calculate unit price from package price"""
        for supplier in self:
            if supplier.dm_is_package_price and supplier.dm_packaging_id and supplier.dm_packaging_id.qty:
                supplier.dm_unit_price_computed = supplier.dm_package_price / supplier.dm_packaging_id.qty
                
                # Sync to standard price field for Odoo compatibility
                supplier.price = supplier.dm_unit_price_computed
            else:
                supplier.dm_unit_price_computed = 0.0
    
    @api.depends('dm_package_price', 'dm_packaging_id', 'product_tmpl_id.weight')
    def _compute_dm_price_per_kg(self):
        """Calculate price per kg from package price"""
        for supplier in self:
            if not supplier.dm_is_package_price or not supplier.dm_packaging_id:
                supplier.dm_price_per_kg = 0.0
                continue
            
            # Get total weight
            if hasattr(supplier.dm_packaging_id, 'packaging_net_weight'):
                total_weight = supplier.dm_packaging_id.packaging_net_weight or 0
            else:
                total_weight = (supplier.dm_packaging_id.qty or 0) * (supplier.product_tmpl_id.weight or 0)
            
            if total_weight > 0:
                supplier.dm_price_per_kg = supplier.dm_package_price / total_weight
            else:
                supplier.dm_price_per_kg = 0.0
    
    # ==========================================
    # OVERRIDE PRICE COMPUTATION
    # ==========================================
    
    @api.onchange('dm_is_package_price', 'dm_package_price', 'dm_packaging_id')
    def _onchange_dm_package_price(self):
        """Sync package price to standard price field"""
        if self.dm_is_package_price and self.dm_package_price and self.dm_packaging_id:
            if self.dm_packaging_id.qty:
                # Set standard price to unit price for Odoo compatibility
                self.price = self.dm_package_price / self.dm_packaging_id.qty
    
    # ==========================================
    # CONSTRAINTS
    # ==========================================
    
    @api.constrains('dm_is_package_price', 'dm_packaging_id', 'dm_package_price')
    def _check_package_pricing(self):
        """Validate package pricing"""
        for supplier in self:
            if supplier.dm_is_package_price:
                if not supplier.dm_packaging_id:
                    raise ValidationError(_("Package type required for package-based pricing"))
                if supplier.dm_package_price <= 0:
                    raise ValidationError(_("Package price must be positive"))
    
    _sql_constraints = [
        ('dm_positive_package_price',
         'CHECK(NOT dm_is_package_price OR dm_package_price > 0)',
         'Package price must be positive!'),
    ]