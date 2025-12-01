# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealLine(models.Model):
    """Deal Line - CORE
    
    Phase 0: Dual parent architecture
    - subdeal_id: Primary parent (execution layer)
    - deal_id: Computed from subdeal for backward compatibility
    
    Restructured v3.1:
    - Field definitions only
    - CRUD methods (create, write, unlink, name_get)
    - Display name computation
    - Compute methods in domain extension files
    """
    _name = 'dm.deal.line'
    _description = 'Deal Line'
    _order = 'sequence, id'
    
    # =========================================================================
    # PARENT RELATIONSHIPS
    # =========================================================================
    
    # Sequencing
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Primary parent: Subdeal (Phase 0)
    subdeal_id = fields.Many2one(
        'dm.deal.subdeal',
        string='Sub-Deal',
        ondelete='cascade',
        index=True,
        help='Parent sub-deal (execution layer)'
    )
    
    # Backward compatible parent: Deal (computed or direct)
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        compute='_compute_deal_id',
        store=True,
        readonly=False,
        index=True,
        help='Parent deal (for backward compatibility and reporting)'
    )
    
    @api.depends('subdeal_id', 'subdeal_id.deal_id')
    def _compute_deal_id(self):
        """Compute deal_id from subdeal, or keep direct value"""
        for line in self:
            if line.subdeal_id:
                line.deal_id = line.subdeal_id.deal_id
            # If no subdeal, keep existing deal_id (backward compat during migration)
    
    currency_id = fields.Many2one(
        'res.currency',
        related='deal_id.currency_id',
        string='Currency',
        store=True
    )
    
    # =========================================================================
    # PRODUCT AND PACKAGING
    # =========================================================================
    
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
    
    # =========================================================================
    # AMOUNTS
    # =========================================================================
    
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
    
    # =========================================================================
    # INVOICING & PROGRESS
    # =========================================================================
    
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
    
    # =========================================================================
    # LINKS TO SO/PO LINES
    # =========================================================================
    
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
    
    # =========================================================================
    # STATE-RELATED FIELDS
    # =========================================================================
    
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
    
    @api.model_create_multi
    def create(self, vals_list):
        """Create deal lines with auto-fetched prices and subdeal linkage"""
        for vals in vals_list:
            # Ensure subdeal exists if deal_id provided without subdeal_id
            if vals.get('deal_id') and not vals.get('subdeal_id'):
                deal = self.env['dm.deal'].browse(vals['deal_id'])
                if deal.primary_subdeal_id:
                    vals['subdeal_id'] = deal.primary_subdeal_id.id
                else:
                    # Create subdeal if needed
                    subdeal = deal._create_primary_subdeal()
                    vals['subdeal_id'] = subdeal.id
            
            # Auto-fetch prices if not provided
            if vals.get('product_id') and vals.get('product_packaging_id'):
                if 'price_packaging_sale' not in vals or not vals.get('price_packaging_sale'):
                    vals['price_packaging_sale'] = self._fetch_customer_price_static(vals)
                if 'price_packaging_purchase' not in vals or not vals.get('price_packaging_purchase'):
                    vals['price_packaging_purchase'] = self._fetch_supplier_price_static(vals)
        
        return super().create(vals_list)
    
    def write(self, vals):
        """Update deal lines with validation"""
        # Lock check - use deal state
        for line in self:
            deal = line.deal_id
            if deal and deal.state not in ['draft', 'validated']:
                locked_fields = {'product_id', 'product_packaging_id', 'quantity_packaging'}
                if set(vals.keys()) & locked_fields:
                    raise UserError(_(
                        'Cannot modify product/packaging/quantity for deal in state "%s".\n'
                        'Deal: %s'
                    ) % (deal.state, deal.name))
        
        res = super().write(vals)
        
        # Sync SO/PO lines if quantities/prices changed
        if any(f in vals for f in ['quantity_packaging', 'price_packaging_sale', 'price_packaging_purchase']):
            for line in self:
                if line.sale_order_line_id:
                    so_line = line.sale_order_line_id
                    so_vals = {}
                    if 'quantity_packaging' in vals:
                        so_vals['product_uom_qty'] = line.quantity_packaging
                    if 'price_packaging_sale' in vals:
                        so_vals['price_unit'] = line.price_packaging_sale
                    if so_vals:
                        so_line.write(so_vals)
                
                if line.purchase_order_line_id:
                    po_line = line.purchase_order_line_id
                    po_vals = {}
                    if 'quantity_packaging' in vals:
                        po_vals['product_qty'] = line.quantity_packaging
                    if 'price_packaging_purchase' in vals:
                        po_vals['price_unit'] = line.price_packaging_purchase
                    if po_vals:
                        po_line.write(po_vals)
        
        return res
    
    def unlink(self):
        """Prevent deletion of lines from locked deals"""
        for line in self:
            deal = line.deal_id
            if deal and deal.state not in ['draft']:
                raise UserError(_(
                    'Cannot delete lines from deal in state "%s".\n'
                    'Deal: %s'
                ) % (deal.state, deal.name))
        
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
    # PRICE FETCH HELPERS (Stubs - full implementation in extension)
    # =========================================================================
    
    @api.model
    def _fetch_customer_price_static(self, vals):
        """
        Static version of price fetch for create().
        Full implementation in dm_deal_line_pricing.py extension.
        """
        return 0.0
    
    @api.model
    def _fetch_supplier_price_static(self, vals):
        """
        Static version of price fetch for create().
        Full implementation in dm_deal_line_pricing.py extension.
        """
        return 0.0
        
class DmDeal(models.Model):
    """Add line_ids relationship to dm.deal"""
    _inherit = 'dm.deal'
    
    line_ids = fields.One2many(
        'dm.deal.line',
        'deal_id',
        string='Deal Lines',
        copy=True
    )          