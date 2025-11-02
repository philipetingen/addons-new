# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealLine(models.Model):
    """Deal Line - CORE
    
    Restructured v3.0:
    - Field definitions only
    - CRUD methods (create, write, unlink, name_get)
    - Display name computation
    - Extensions in domain files
    """
    _name = 'dm.deal.line'
    _description = 'Deal Line'
    _order = 'sequence, id'
    
    # =========================================================================
    # FIELDS
    # =========================================================================
    
    # Sequencing
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Parent deal
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='deal_id.currency_id',
        string='Currency',
        store=True,
        readonly=True
    )    
    
    # Product and packaging
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('sale_ok', '=', True)]
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Packaging',
        required=True,
        domain="[('product_id', '=', product_id)]"
    )
    
    packaging_uom_id = fields.Many2one(
        'uom.uom',
        string='Package UoM',
        compute='_compute_packaging_uom',
        store=True,
        readonly=True
    )
    
    # Customer product codes
    customer_product_code = fields.Char(
        string='Customer Product Code',
        help='Customer\'s code for this product'
    )
    
    customer_product_description = fields.Text(
        string='Customer Description',
        help='Customer\'s description for this product'
    )

    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('is_company', '=', True), ('supplier_rank', '>', 0)],
        help='Supplier determined from vendor pricing for this product'
    )
    
    # =========================================================================
    # WEIGHT ENTRY ENHANCEMENT - Sprint 2.4
    # =========================================================================
    
    # Entry mode for quantity input
    entry_mode = fields.Selection([
        ('pkg', 'By Package'),
        ('kg', 'By Weight (kg)')
    ], string='Entry Mode', default='pkg', required=True)
    
    # Package-native quantities (PRIMARY)
    quantity_packaging = fields.Float(
        string='Qty (Packages)',
        digits=(16, 3),
        required=True,
        default=1.0
    )
    
    # Weight field - dual purpose (entry in kg mode, display in pkg mode)
    weight = fields.Float(
        string='Weight (kg)',
        digits=(16, 3),
        help='Enter weight in kg mode, or displays calculated weight in package mode'
    )
    
    # Unit quantities (COMPUTED REFERENCE ONLY)
    quantity_units = fields.Float(
        string='Qty (Units)',
        compute='_compute_quantities',
        store=True,
        digits=(16, 3),
        help='Reference only - calculated from packages'
    )
    
    # Container type from product
    container_type_id = fields.Many2one(
        'dm.container.type',
        string='Container Type',
        compute='_compute_container_type',
        store=True
    )
    
    # =========================================================================
    # CONTAINER CALCULATIONS - Sprint 4 (Package Configuration Extension)
    # =========================================================================
    
    containers_required = fields.Float(
        string='Containers Required',
        compute='_compute_containers_required',
        store=True,
        readonly=False,  # User can override
        digits=(16, 3),
        help='Number of containers needed (auto-calculated, can override)'
    )
    
    container_calculation_method = fields.Selection([
        ('manual', 'Manual Entry'),
        ('packaging', 'From Packaging Hierarchy'),
        ('volume', 'From Volume'),
        ('weight', 'From Weight')
    ], string='Calculation Method',
        compute='_compute_container_calculation_method',
        store=True,
        help='Shows how containers were calculated'
    )
    
    container_teu = fields.Float(
        string='TEU',
        compute='_compute_container_teu',
        store=True,
        digits=(16, 2),
        help='Twenty-foot Equivalent Units for capacity planning'
    )
    
    container_calculation_warning = fields.Char(
        string='Calculation Warning',
        compute='_compute_container_calculation_warning',
        help='Warnings about missing data or calculation issues'
    )
    
    # =========================================================================
    # PRODUCTION TRACKING
    # =========================================================================
    
    quantity_produced = fields.Float(
        string='Qty Produced',
        digits=(16, 3),
        readonly=True,
        help='Actual quantity produced (set by production module)'
    )
    
    production_status = fields.Selection([
        ('not_started', 'Not Started'),
        ('partial', 'Partial'),
        ('complete', 'Complete')
    ], string='Production Status',
        compute='_compute_production_status',
        store=True
    )
    
    # =========================================================================
    # SALES PRICING (6-decimal precision)
    # =========================================================================

    price_packaging_sale = fields.Float(
        string='Sale Price/Package',
        digits=(16, 6),
        required=True
    )
    
    price_unit_sale = fields.Float(
        string='Sale Price/Unit',
        compute='_compute_prices',
        store=True,
        digits=(16, 6),
        help='Reference only - calculated from package price'
    )
    
    price_per_kg_sale = fields.Float(
        string='Sale Price/kg',
        compute='_compute_prices',
        store=True,
        digits=(16, 3)
    )
    
    # Purchase pricing
    price_packaging_purchase = fields.Float(
        string='Purchase Price/Package',
        digits=(16, 6)
    )
    
    price_unit_purchase = fields.Float(
        string='Purchase Price/Unit',
        compute='_compute_prices',
        store=True,
        digits=(16, 6),
        help='Reference only - calculated from package price'
    )
    
    price_per_kg_purchase = fields.Float(
        string='Purchase Price/kg',
        compute='_compute_prices',
        store=True,
        digits=(16, 3)
    )
    
    # Amounts
    amount_sale = fields.Float(
        string='Sale Amount',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    amount_purchase = fields.Float(
        string='Purchase Amount',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    # Margin
    margin_amount = fields.Float(
        string='Margin',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    margin_percentage = fields.Float(
        string='Margin %',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    # Tracking quantities through stages
    quantity_loaded = fields.Float(
        string='Loaded (Packages)',
        digits=(16, 3),
        readonly=True,
        help='Quantity actually loaded for shipping'
    )
    
    quantity_invoiced = fields.Float(
        string='Invoiced (Packages)',
        digits=(16, 3),
        readonly=True,
        help='Quantity invoiced to customer'
    )
    
    production_progress = fields.Float(
        string='Production %',
        compute='_compute_progress',
        store=True,
        digits=(5, 2)
    )
    
    # Links to SO/PO lines
    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string='SO Line',
        readonly=True
    )
    
    purchase_order_line_id = fields.Many2one(
        'purchase.order.line',
        string='PO Line',
        readonly=True
    )
    
    # State-related fields
    deal_state = fields.Selection(
        related='deal_id.state',
        string='Deal Status',
        store=True
    )

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=False
    )
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # =========================================================================
    # COMPUTED METHODS - CORE ONLY
    # =========================================================================
    
    @api.depends('product_id', 'product_packaging_id', 'quantity_packaging')
    def _compute_display_name(self):
        for line in self:
            if not line.product_id:
                line.display_name = 'New Line'
                continue
            
            parts = [line.product_id.name]
            
            if line.product_packaging_id:
                parts.append(f"({line.product_packaging_id.name})")
            
            if line.quantity_packaging:
                parts.append(f"× {line.quantity_packaging:.1f}")
            
            line.display_name = ' '.join(parts)
    
    # =========================================================================
    # CRUD METHODS
    # =========================================================================
    
    @api.model
    def create(self, vals_list):
        """Create deal lines with auto-fetched prices"""
        if not isinstance(vals_list, list):
            vals_list = [vals_list]
        
        for vals in vals_list:
            # Auto-fetch prices if not provided
            if 'product_id' in vals and 'product_packaging_id' in vals:
                if 'price_packaging_sale' not in vals:
                    vals['price_packaging_sale'] = self._fetch_customer_price_static(vals)
                if 'price_packaging_purchase' not in vals:
                    vals['price_packaging_purchase'] = self._fetch_supplier_price_static(vals)
        
        return super().create(vals_list)
    
    def write(self, vals):
        """Update deal lines with validation"""
        # Lock check
        for line in self:
            if line.deal_id and line.deal_id.state not in ['draft', 'confirmed']:
                locked_fields = {'product_id', 'product_packaging_id', 'quantity_packaging'}
                if set(vals.keys()) & locked_fields:
                    raise UserError(_(
                        'Cannot modify product/packaging/quantity for deal in state "%s"'
                    ) % line.deal_id.state)
        
        res = super().write(vals)
        
        # Refresh SO/PO lines if quantities changed
        if 'quantity_packaging' in vals or 'price_packaging_sale' in vals or 'price_packaging_purchase' in vals:
            for line in self:
                if line.sale_order_line_id:
                    line.sale_order_line_id.product_uom_qty = line.quantity_packaging
                    line.sale_order_line_id.price_unit = line.price_packaging_sale
                
                if line.purchase_order_line_id:
                    line.purchase_order_line_id.product_qty = line.quantity_packaging
                    line.purchase_order_line_id.price_unit = line.price_packaging_purchase
        
        return res
    
    def unlink(self):
        """Prevent deletion of lines from locked deals"""
        for line in self:
            if line.deal_id and line.deal_id.state not in ['draft']:
                raise UserError(_(
                    'Cannot delete lines from deal in state "%s"'
                ) % line.deal_id.state)
        
        return super().unlink()
    
    def name_get(self):
        """Display deal line in smart format"""
        result = []
        for line in self:
            if not line.product_id:
                name = 'New Line'
            else:
                name = f"{line.product_id.name}"
                if line.product_packaging_id:
                    name += f" ({line.product_packaging_id.name})"
                if line.quantity_packaging:
                    name += f" × {line.quantity_packaging:.1f}"
            
            result.append((line.id, name))
        
        return result
    
    # =========================================================================
    # STATIC HELPER METHODS FOR CREATE
    # =========================================================================
    
    @api.model
    def _fetch_customer_price_static(self, vals):
        """Static version of price fetch for create()"""
        # Simplified version - full implementation in dm_deal_line_pricing.py
        return 0.0
    
    @api.model
    def _fetch_supplier_price_static(self, vals):
        """Static version of price fetch for create()"""
        # Simplified version - full implementation in dm_deal_line_pricing.py
        return 0.0