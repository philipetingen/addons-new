from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmPackageMixin(models.AbstractModel):
    """
    Simplified package-native mixin without UoM auto-creation.
    Uses product.packaging records directly.
    """
    _name = 'dm.package.mixin'
    _description = 'DonnaMello Package Management Mixin'
    
    # Package-native fields
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        tracking=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Packaging',
        domain="[('product_id', '=', product_id)]",
        help='Package type (carton, box, pallet, etc.)'
    )
    
    # PRIMARY quantity field - always in packages
    quantity_packaging = fields.Float(
        string='Qty (Packages)',
        digits=(16, 3),
        required=True,
        tracking=True,
        help='Quantity in packages (cartons, boxes, etc.)'
    )
    
    # Reference fields - computed from packages
    quantity_units = fields.Float(
        string='Qty (Units)',
        compute='_compute_quantity_units',
        store=True,
        digits=(16, 3),
        help='Reference quantity in individual units'
    )
    
    quantity_kg = fields.Float(
        string='Qty (kg)',
        compute='_compute_quantity_kg',
        store=True,
        digits=(16, 3),
        help='Total net weight in kilograms'
    )
    
    # Volume calculations
    total_cbm = fields.Float(
        string='Total CBM',
        compute='_compute_volume',
        store=True,
        digits=(16, 3),
        help='Total volume in cubic meters'
    )
    
    # Dual entry mode support
    entry_mode = fields.Selection([
        ('pkg', 'By Package'),
        ('kg', 'By Weight'),
        ('units', 'By Units')
    ], default='pkg', string='Entry Mode')
    
    entry_quantity = fields.Float(
        string='Entry Quantity',
        digits=(16, 3),
        help='Quantity in selected entry mode'
    )
    
    @api.depends('quantity_packaging', 'product_packaging_id', 'product_packaging_id.total_product_qty')
    def _compute_quantity_units(self):
        """Compute unit quantity from package quantity using hierarchy."""
        for record in self:
            if record.quantity_packaging and record.product_packaging_id:
                # Use total_product_qty which includes hierarchy
                record.quantity_units = record.quantity_packaging * (record.product_packaging_id.total_product_qty or record.product_packaging_id.qty)
            else:
                record.quantity_units = 0.0
    
    @api.depends('quantity_packaging', 'product_packaging_id', 'product_packaging_id.packaging_net_weight')
    def _compute_quantity_kg(self):
        """Compute total net weight from package quantity."""
        for record in self:
            if record.quantity_packaging and record.product_packaging_id:
                # Use packaging_net_weight which cascades through hierarchy
                record.quantity_kg = record.quantity_packaging * (record.product_packaging_id.packaging_net_weight or 0)
            else:
                record.quantity_kg = 0.0
    
    @api.depends('quantity_packaging', 'product_packaging_id', 'product_packaging_id.packaging_volume_m3')
    def _compute_volume(self):
        """Compute total volume using packaging CBM."""
        for record in self:
            if record.quantity_packaging and record.product_packaging_id:
                record.total_cbm = record.quantity_packaging * (record.product_packaging_id.packaging_volume_m3 or 0)
            else:
                record.total_cbm = 0.0
    
    @api.onchange('entry_mode', 'entry_quantity', 'product_packaging_id')
    def _onchange_entry_quantity(self):
        """Convert entry quantity to package quantity based on entry mode."""
        if not self.entry_quantity or not self.product_packaging_id:
            return
        
        if self.entry_mode == 'pkg':
            # Direct package entry
            self.quantity_packaging = self.entry_quantity
            
        elif self.entry_mode == 'units':
            # Convert units to packages
            total_qty = self.product_packaging_id.total_product_qty or self.product_packaging_id.qty
            if total_qty:
                self.quantity_packaging = self.entry_quantity / total_qty
            else:
                raise UserError("Package quantity not defined for this packaging")
                
        elif self.entry_mode == 'kg':
            # Convert kg to packages using net weight
            net_weight = self.product_packaging_id.packaging_net_weight
            if net_weight:
                self.quantity_packaging = self.entry_quantity / net_weight
            else:
                raise UserError("Package net weight not defined")
    
    def validate_package_quantities(self):
        """Validate that package quantities are consistent."""
        for record in self:
            if not record.product_packaging_id:
                raise UserError(f"Packaging must be specified for {record.product_id.display_name}")
            
            if record.quantity_packaging <= 0:
                raise UserError(f"Package quantity must be positive for {record.product_id.display_name}")
        
        return True
    
    def get_package_display(self):
        """
        Get formatted package quantity display with hierarchy info.
        Example: "10 Master Cartons (2,400 units, 240 kg)"
        """
        self.ensure_one()
        
        if not self.product_packaging_id:
            return f"{self.quantity_packaging:.3f} packages"
        
        package_str = f"{self.quantity_packaging:.3f} {self.product_packaging_id.name}"
        
        # Add standard type if available
        if self.product_packaging_id.standard_type_id:
            package_str = f"{self.quantity_packaging:.3f} {self.product_packaging_id.standard_type_id.name}s"
        
        # Add unit count
        if self.quantity_units:
            package_str += f" ({self.quantity_units:.0f} units)"
        
        # Add weight
        if self.quantity_kg > 0:
            package_str += f" [{self.quantity_kg:.1f} kg]"
        
        return package_str