# -*- coding: utf-8 -*-
"""
MERGED Product Packaging Extension
===================================

Combines:
1. Hierarchical packaging from dm_master_data (Document 6)
2. packaging_uom_id auto-creation from dm_deal (Document 7)

This is the CORRECT version that should be in dm_master_data module.

Version: v17.0.4.0.0
Module: dm_master_data
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProductPackaging(models.Model):
    """
    Enhanced product packaging with:
    - Hierarchical structure (parent/child packages)
    - Auto-created package UoM for SO/PO integration
    - Weight and volume cascades
    - Package-native operations support
    """
    _inherit = 'product.packaging'
    
    # ==========================================
    # CRITICAL FIX: PACKAGE UOM FOR SO/PO
    # ==========================================
    
    uom_id = fields.Many2one(
        'uom.uom',
        string='Package UoM',
        compute='_compute_packaging_uom',
        store=True,
        readonly=True,
        copy=False,
        help='Auto-created Unit of Measure for this packaging. Used in SO/PO to preserve package quantities.'
    )
    
    # Also add as packaging_uom_id for backwards compatibility
    packaging_uom_id = fields.Many2one(
        'uom.uom',
        string='Package UoM (Legacy)',
        related='uom_id',
        store=False,
        help='Alias for uom_id for backwards compatibility'
    )
    
    # ==========================================
    # STANDARD TYPE MAPPING
    # ==========================================
    
    standard_type_id = fields.Many2one(
        'packaging.standard.type',
        string='Standard Type',
        help='Map this packaging to a standard type for reporting and integration'
    )
    
    standard_type_code = fields.Char(
        string='Standard Type Code',
        related='standard_type_id.code',
        store=True,
        help='Standard type code for quick filtering'
    )
    
    # ==========================================
    # HIERARCHICAL PACKAGING
    # ==========================================
    
    package_uom_type = fields.Selection([
        ('product', 'Product Units'),
        ('package', 'Other Package')
    ], string='Contains', 
       default='product', 
       required=True,
       help='Choose whether this packaging contains product units or other packages'
    )
    
    parent_package_id = fields.Many2one(
        'product.packaging',
        string='Parent Package',
        help='Select which package type this packaging contains',
        domain="[('product_id', '=', parent.product_id), ('id', '!=', parent.id)]"
    )
    
    effective_unit_name = fields.Char(
        string='Unit Name',
        compute='_compute_effective_unit_name',
        store=True,
        help='Shows either the product UoM or the parent package name'
    )
    
    total_product_qty = fields.Float(
        string='Total Product Units',
        compute='_compute_total_product_qty',
        store=True,
        help='Total quantity of base product units contained in this package'
    )
    
    # ==========================================
    # PHYSICAL DIMENSIONS (in centimeters)
    # ==========================================
    
    packaging_length = fields.Float(
        string='Length (cm)',
        help='Package length in centimeters',
        digits=(12, 2)
    )
    
    packaging_width = fields.Float(
        string='Width (cm)', 
        help='Package width in centimeters',
        digits=(12, 2)
    )
    
    packaging_height = fields.Float(
        string='Height (cm)',
        help='Package height in centimeters', 
        digits=(12, 2)
    )
    
    packaging_volume_m3 = fields.Float(
        string='Volume (m³)',
        help='Volume of the packaging in cubic meters',
        digits=(12, 6),
        compute='_compute_packaging_volume',
        store=True,
        readonly=False  # Allow manual override
    )
    
    auto_calculate_volume = fields.Boolean(
        string='Auto-calculate Volume',
        default=True,
        help='Automatically calculate volume from dimensions'
    )
    
    # ==========================================
    # WEIGHT FIELDS (in kilograms)
    # ==========================================
    
    packaging_weight = fields.Float(
        string='Package Weight (kg)',
        help='Weight of the packaging material itself (tare weight)',
        digits='Stock Weight'
    )
    
    packaging_net_weight = fields.Float(
        string='Net Weight (kg)',
        help='Net weight of the contents (product only, excluding packaging)',
        digits='Stock Weight',
        compute='_compute_net_weight',
        store=True,
        readonly=False  # Allow manual override
    )
    
    packaging_gross_weight = fields.Float(
        string='Gross Weight (kg)', 
        help='Total weight (net weight + package weight)',
        digits='Stock Weight',
        compute='_compute_gross_weight',
        store=True,
        readonly=False  # Allow manual override
    )
    
    auto_calculate_gross_weight = fields.Boolean(
        string='Auto-calculate Gross Weight',
        default=True,
        help='Automatically calculate gross weight as net + package weight'
    )
    
    auto_calculate_net_weight = fields.Boolean(
        string='Auto-calculate Net Weight',
        default=True,
        help='Automatically calculate net weight from parent package or product'
    )
    
    # ==========================================
    # ADDITIONAL ATTRIBUTES
    # ==========================================
    
    stackable = fields.Boolean(
        string='Stackable',
        default=True,
        help='Can this package be stacked'
    )
    
    max_stacking = fields.Integer(
        string='Max Stack Height',
        default=0,
        help='Maximum units that can be stacked (0 = unlimited)'
    )
    
    is_pallet = fields.Boolean(
        string='Is Pallet',
        default=False,
        help='This packaging is a pallet'
    )
    
    packages_per_pallet = fields.Integer(
        string='Packages per Pallet',
        help='Number of packages that fit on a pallet'
    )
    
    layers_per_pallet = fields.Integer(
        string='Layers per Pallet',
        help='Number of layers on a pallet'
    )
    
    # ==========================================
    # COMPUTED METHODS - PACKAGE UOM
    # ==========================================
    
    @api.depends('name', 'product_id', 'qty')
    def _compute_packaging_uom(self):
        """
        CRITICAL: Auto-create UoM for each packaging.
        This UoM is what gets used in SO/PO lines!
        
        Creates UoM with name like "Carton (Mango Gummy Peelable)"
        """
        UoM = self.env['uom.uom']
        
        for pack in self:
            # Skip if no product or name
            if not pack.product_id or not pack.name:
                pack.uom_id = False
                continue
            
            # Construct UoM name
            uom_name = f"{pack.name} ({pack.product_id.name})"
            
            # Check if UoM already exists
            existing_uom = UoM.search([
                ('name', '=', uom_name)
            ], limit=1)
            
            if existing_uom:
                # Update factor if qty changed
                if existing_uom.factor_inv != (pack.qty or 1):
                    try:
                        existing_uom.write({'factor_inv': pack.qty or 1})
                        _logger.info(
                            f"✓ Updated UoM '{uom_name}' factor to {pack.qty}"
                        )
                    except Exception as e:
                        _logger.warning(
                            f"Could not update UoM factor for '{uom_name}': {e}"
                        )
                
                pack.uom_id = existing_uom
            else:
                # Create new UoM
                try:
                    unit_category = self.env.ref('uom.product_uom_categ_unit')
                    
                    uom_vals = {
                        'name': uom_name,
                        'category_id': unit_category.id,
                        'uom_type': 'bigger',  # Package is always bigger than unit
                        'factor_inv': pack.qty if pack.qty and pack.qty > 0 else 1.0,
                        'rounding': 0.001,  # 3 decimal precision
                        'active': True,
                    }
                    
                    new_uom = UoM.create(uom_vals)
                    pack.uom_id = new_uom
                    
                    _logger.info(
                        f"✓ Created UoM '{uom_name}' for packaging '{pack.name}' "
                        f"(1 pkg = {pack.qty} units)"
                    )
                    
                except Exception as e:
                    _logger.error(
                        f"✗ Failed to create UoM for packaging '{pack.name}': {e}"
                    )
                    pack.uom_id = False
    
    # ==========================================
    # COMPUTED METHODS - HIERARCHY
    # ==========================================
    
    @api.depends('package_uom_type', 'parent_package_id', 'product_id')
    def _compute_effective_unit_name(self):
        """Compute the effective unit name based on UoM type"""
        for record in self:
            if record.package_uom_type == 'package' and record.parent_package_id:
                record.effective_unit_name = record.parent_package_id.name
            elif record.product_id and record.product_id.uom_id:
                record.effective_unit_name = record.product_id.uom_id.name
            else:
                record.effective_unit_name = 'Units'
    
    @api.depends('package_uom_type', 'parent_package_id', 'qty', 'parent_package_id.total_product_qty')
    def _compute_total_product_qty(self):
        """Compute total product quantity considering package hierarchy"""
        for record in self:
            if record.package_uom_type == 'product':
                # Direct product units
                record.total_product_qty = record.qty
            elif record.package_uom_type == 'package' and record.parent_package_id:
                # Calculate based on parent's total product quantity
                parent_total = record.parent_package_id.total_product_qty or record.parent_package_id.qty
                record.total_product_qty = record.qty * parent_total
            else:
                record.total_product_qty = record.qty
    
    # ==========================================
    # COMPUTED METHODS - VOLUME
    # ==========================================
    
    @api.depends('packaging_width', 'packaging_length', 'packaging_height', 
                 'auto_calculate_volume', 'package_uom_type', 'parent_package_id', 
                 'parent_package_id.packaging_volume_m3', 'qty')
    def _compute_packaging_volume(self):
        """
        Calculate volume from dimensions in cm, result in m³.
        
        Enhanced to cascade from parent packages:
        - If dimensions (L×W×H) provided → calculate from dimensions (most accurate)
        - Else if parent package → cascade from parent volume × qty (good estimate)
        - Else → keep manual value or default to 0
        """
        for record in self:
            if not record.auto_calculate_volume:
                # Manual mode - don't compute
                continue
            
            # Priority 1: Calculate from dimensions if all are available (most accurate)
            if record.packaging_width and record.packaging_length and record.packaging_height:
                # Volume in cm³
                volume_cm3 = record.packaging_width * record.packaging_length * record.packaging_height
                # Convert to m³
                record.packaging_volume_m3 = volume_cm3 / 1000000.0
                
            # Priority 2: Cascade from parent package (good estimate)
            elif (record.package_uom_type == 'package' and 
                  record.parent_package_id and 
                  record.parent_package_id.packaging_volume_m3 and
                  record.qty):
                # Calculate: qty packages × volume per package = total volume
                parent_volume = record.parent_package_id.packaging_volume_m3
                record.packaging_volume_m3 = parent_volume * record.qty
                
            # Priority 3: Keep existing or default to 0
            elif not record.packaging_volume_m3:
                record.packaging_volume_m3 = 0.0
    
    # ==========================================
    # COMPUTED METHODS - WEIGHT CASCADE
    # ==========================================
    
    @api.depends('packaging_net_weight', 'packaging_weight', 'auto_calculate_gross_weight')
    def _compute_gross_weight(self):
        """Auto-calculate gross weight when component weights change"""
        for record in self:
            if record.auto_calculate_gross_weight:
                net = record.packaging_net_weight or 0
                package = record.packaging_weight or 0
                record.packaging_gross_weight = net + package
    
    @api.depends('package_uom_type', 'parent_package_id', 'parent_package_id.packaging_net_weight', 
                 'qty', 'product_id', 'product_id.weight', 'auto_calculate_net_weight')
    def _compute_net_weight(self):
        """
        Auto-calculate net weight from parent package or product.
        This is the CRITICAL cascade logic.
        """
        for record in self:
            if not record.auto_calculate_net_weight:
                continue
                
            if record.package_uom_type == 'product' and record.product_id and record.qty:
                # Base case: Calculate from product weight
                # qty units × weight per unit = total net weight
                record.packaging_net_weight = record.qty * (record.product_id.weight or 0)
                
            elif (record.package_uom_type == 'package' and 
                  record.parent_package_id and 
                  record.qty):
                # Nested case: Calculate from parent package net weight
                # qty packages × net weight per package = total net weight
                parent_net = record.parent_package_id.packaging_net_weight or 0
                record.packaging_net_weight = parent_net * record.qty
                
            elif not record.packaging_net_weight:
                record.packaging_net_weight = 0.0
    
    # ==========================================
    # HELPER METHODS FOR PACKAGE-NATIVE OPERATIONS
    # ==========================================
    
    def get_effective_quantity_for_calculation(self):
        """Return the appropriate quantity for price calculations"""
        self.ensure_one()
        return self.total_product_qty if self.total_product_qty else self.qty
    
    def calculate_unit_price_from_packaging_price(self, packaging_price):
        """Calculate unit price preserving 6-decimal precision"""
        self.ensure_one()
        
        if not packaging_price:
            return 0.0
        
        effective_qty = self.get_effective_quantity_for_calculation()
        if not effective_qty:
            _logger.warning(f"Cannot calculate unit price for packaging '{self.name}' - no effective quantity")
            return 0.0
        
        return packaging_price / effective_qty
    
    def calculate_packaging_price_from_unit_price(self, unit_price):
        """Calculate packaging price preserving precision"""
        self.ensure_one()
        
        if not unit_price:
            return 0.0
        
        effective_qty = self.get_effective_quantity_for_calculation()
        return unit_price * effective_qty
    
    def get_price_per_kg(self, packaging_price):
        """
        Calculate price per kg from package price.
        Uses net weight for market-standard pricing.
        """
        self.ensure_one()
        
        if not packaging_price or not self.packaging_net_weight:
            return 0.0
        
        return packaging_price / self.packaging_net_weight
    
    # ==========================================
    # ONCHANGE METHODS
    # ==========================================
    
    @api.onchange('package_uom_type')
    def _onchange_package_uom_type(self):
        """Clear parent package when switching to product units"""
        if self.package_uom_type == 'product':
            self.parent_package_id = False
    
    @api.onchange('standard_type_id')
    def _onchange_standard_type(self):
        """Auto-set pallet flag when selecting pallet type"""
        if self.standard_type_id:
            if self.standard_type_id.category == 'pallet':
                self.is_pallet = True
    
    # ==========================================
    # VALIDATION CONSTRAINTS
    # ==========================================
    
    @api.constrains('parent_package_id', 'product_id')
    def _check_parent_package_product(self):
        """Ensure parent package belongs to the same product"""
        for record in self:
            if (record.parent_package_id and 
                record.parent_package_id.product_id != record.product_id):
                raise ValidationError(
                    f"Parent package must belong to the same product ({record.product_id.name})"
                )
    
    @api.constrains('parent_package_id')
    def _check_package_hierarchy_loop(self):
        """Prevent circular references in package hierarchy"""
        for record in self:
            if record.parent_package_id:
                current = record.parent_package_id
                visited = {record.id}
                while current:
                    if current.id in visited:
                        raise ValidationError(
                            f"Circular reference detected in package hierarchy for '{record.name}'"
                        )
                    visited.add(current.id)
                    current = current.parent_package_id
    
    @api.constrains('qty')
    def _check_qty_positive(self):
        """Ensure package quantity is positive."""
        for pack in self:
            if pack.qty <= 0:
                raise ValidationError(f"Package quantity must be positive for {pack.name}")
    
    # ==========================================
    # MANUAL ACTIONS
    # ==========================================
    
    def action_recreate_uom(self):
        """
        Manual action to recreate/update UoM for selected packagings.
        Useful when bulk-fixing existing packaging records.
        """
        for packaging in self:
            # Force recompute
            packaging._compute_packaging_uom()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'UoM Updated',
                'message': f'{len(self)} packaging UoM(s) have been recreated/updated.',
                'type': 'success',
                'sticky': False,
            }
        }