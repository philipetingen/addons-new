from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmPriceCalculationMixin(models.AbstractModel):
    """
    Price calculation mixin with 6-decimal precision.
    
    Updated to align with dm_master_data packaging:
    - Support for packaging hierarchy in calculations
    - Enhanced price/kg calculations
    - Integration with new packaging UoM structure
    """
    _name = 'dm.price.calculation.mixin'
    _description = 'DonnaMello Price Calculation Mixin'
    
    # Package pricing (SOURCE OF TRUTH)
    price_packaging = fields.Float(
        string='Price/Package',
        digits=(16, 6),
        required=True,
        help='Price per package - SOURCE OF TRUTH'
    )
    
    # Computed reference prices
    price_unit = fields.Float(
        string='Price/Unit',
        compute='_compute_price_unit',
        store=True,
        digits=(16, 6),
        help='Computed price per individual unit'
    )
    
    price_per_kg = fields.Float(
        string='Price/kg',
        compute='_compute_price_per_kg',
        store=True,
        digits=(16, 3),
        help='Computed price per kilogram'
    )
    
    # Total calculations
    total_amount = fields.Float(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,
        digits=(16, 2),
        help='Total price (packages × price/package)'
    )
    
    @api.depends('price_packaging', 'product_packaging_id')
    def _compute_price_unit(self):
        """
        Compute unit price from package price.
        Updated to use packaging hierarchy.
        """
        for record in self:
            if record.price_packaging and record.product_packaging_id:
                # Use total_qty if available (includes hierarchy)
                qty = getattr(record.product_packaging_id, 'total_qty', None)
                if not qty:
                    qty = getattr(record.product_packaging_id, 'qty', None)
                
                if qty and qty > 0:
                    record.price_unit = record.price_packaging / qty
                else:
                    record.price_unit = record.price_packaging
            else:
                record.price_unit = 0.0
    
    @api.depends('price_packaging', 'product_packaging_id', 'product_id.weight')
    def _compute_price_per_kg(self):
        """
        Compute price per kg from package price.
        Updated for packaging hierarchy and total weight calculations.
        """
        for record in self:
            if (record.price_packaging and 
                record.product_packaging_id and 
                record.product_id and
                record.product_id.weight):
                
                # Get total units in package (with hierarchy)
                qty = getattr(record.product_packaging_id, 'total_qty', None)
                if not qty:
                    qty = getattr(record.product_packaging_id, 'qty', 1)
                
                # Check for pre-calculated weight on packaging
                if hasattr(record.product_packaging_id, 'total_product_weight'):
                    total_weight_kg = record.product_packaging_id.total_product_weight
                else:
                    total_weight_kg = qty * record.product_id.weight
                
                if total_weight_kg > 0:
                    record.price_per_kg = record.price_packaging / total_weight_kg
                else:
                    record.price_per_kg = 0.0
            else:
                record.price_per_kg = 0.0
    
    @api.depends('quantity_packaging', 'price_packaging')
    def _compute_total_amount(self):
        """
        Compute total amount from package quantity and price.
        No rounding errors as we use package-native calculation.
        """
        for record in self:
            record.total_amount = record.quantity_packaging * record.price_packaging
    
    def convert_price_from_kg(self, price_per_kg):
        """
        Convert price per kg to package price.
        Updated for new packaging structure.
        """
        self.ensure_one()
        
        if not self.product_packaging_id or not self.product_id.weight:
            raise UserError("Cannot convert price/kg without packaging and product weight")
        
        # Use hierarchy-aware quantity
        qty = getattr(self.product_packaging_id, 'total_qty', None)
        if not qty:
            qty = getattr(self.product_packaging_id, 'qty', 1)
        
        # Check for pre-calculated weight
        if hasattr(self.product_packaging_id, 'total_product_weight'):
            total_weight = self.product_packaging_id.total_product_weight
        else:
            total_weight = qty * self.product_id.weight
        
        return price_per_kg * total_weight
    
    def convert_price_from_units(self, price_per_unit):
        """
        Convert price per unit to package price.
        Updated for packaging hierarchy.
        """
        self.ensure_one()
        
        if not self.product_packaging_id:
            raise UserError("Cannot convert unit price without packaging")
        
        # Use total_qty for hierarchy support
        qty = getattr(self.product_packaging_id, 'total_qty', None)
        if not qty:
            qty = getattr(self.product_packaging_id, 'qty', 1)
        
        return price_per_unit * qty
    
    @api.onchange('entry_mode', 'entry_price')
    def _onchange_entry_price(self):
        """
        Convert entered price to package price based on entry mode.
        Supports dual entry for user convenience.
        """
        if not hasattr(self, 'entry_mode') or not hasattr(self, 'entry_price'):
            return
        
        if not self.entry_price:
            return
        
        if self.entry_mode == 'pkg':
            self.price_packaging = self.entry_price
            
        elif self.entry_mode == 'units':
            self.price_packaging = self.convert_price_from_units(self.entry_price)
            
        elif self.entry_mode == 'kg':
            self.price_packaging = self.convert_price_from_kg(self.entry_price)
    
    def validate_prices(self):
        """
        Validate that all prices are non-negative.
        Enhanced with better error reporting.
        """
        for record in self:
            if record.price_packaging < 0:
                product_name = record.product_id.display_name if record.product_id else 'Unknown'
                raise UserError(
                    f"Package price cannot be negative for {product_name}: "
                    f"{record.price_packaging:.6f}"
                )
        
        return True
    
    def get_price_display(self):
        """
        Get formatted price display with all conversions.
        Enhanced with packaging type info.
        """
        self.ensure_one()
        
        display_parts = []
        
        # Package price (primary)
        if self.product_packaging_id:
            pkg_name = self.product_packaging_id.name
            # Add standard type if available
            if hasattr(self.product_packaging_id, 'standard_type_id') and self.product_packaging_id.standard_type_id:
                pkg_name = f"{self.product_packaging_id.standard_type_id.name}"
            
            display_parts.append(
                f"{self.price_packaging:.6f}/{pkg_name}"
            )
        else:
            display_parts.append(f"{self.price_packaging:.6f}/package")
        
        # Unit price (reference)
        if self.price_unit:
            display_parts.append(f"({self.price_unit:.6f}/unit)")
        
        # Price per kg (reference)  
        if self.price_per_kg:
            display_parts.append(f"[{self.price_per_kg:.3f}/kg]")
        
        return " ".join(display_parts)
    
    def get_margin_info(self):
        """
        Calculate margin information if sale and purchase prices exist.
        New method for deal management integration.
        """
        margin_info = {}
        
        if hasattr(self, 'price_packaging_sale') and hasattr(self, 'price_packaging_purchase'):
            margin_amount = self.price_packaging_sale - self.price_packaging_purchase
            margin_info['amount'] = margin_amount
            
            if self.price_packaging_sale > 0:
                margin_info['percentage'] = (margin_amount / self.price_packaging_sale) * 100
            else:
                margin_info['percentage'] = 0.0
            
            # Per kg margin
            if hasattr(self, 'price_per_kg_sale') and hasattr(self, 'price_per_kg_purchase'):
                margin_info['per_kg'] = self.price_per_kg_sale - self.price_per_kg_purchase
        
        return margin_info