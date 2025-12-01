# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDealLineLot(models.Model):
    """Deal Line Lot - Production lot tracking at deal line level
    
    Renamed from dm.deal.lot to dm.deal.line.lot for clarity.
    Each lot record represents a portion of a deal line with specific lot number.
    """
    _name = 'dm.deal.line.lot'
    _description = 'Deal Line Production Lot Detail'
    _order = 'deal_line_id, sequence, id'
    
    # ========================================================================
    # HEADER
    # ========================================================================
    
    deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    deal_id = fields.Many2one(
        'dm.deal',
        related='deal_line_id.deal_id',
        string='Deal',
        store=True,
        readonly=True,
        index=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    state = fields.Selection(
        related='deal_id.state',
        string='Deal State',
        store=True,
        readonly=True
    )
    
    # ========================================================================
    # PRODUCT INFO (RELATED)
    # ========================================================================
    
    product_id = fields.Many2one(
        'product.product',
        related='deal_line_id.product_id',
        string='Product',
        store=True,
        readonly=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        related='deal_line_id.product_packaging_id',
        string='Package Type',
        store=True,
        readonly=True
    )
    
    packaging_qty = fields.Float(
        related='product_packaging_id.qty',
        string='Units/Package',
        readonly=True
    )
    
    # ========================================================================
    # LOT IDENTIFICATION
    # ========================================================================
    
    lot_number = fields.Char(
        string='Lot/Batch Number',
        required=True,
        index=True,
        tracking=True,
        help='Factory lot or batch number'
    )
    
    # ========================================================================
    # QUANTITY (PACKAGE-NATIVE)
    # ========================================================================
    
    quantity = fields.Float(
        string='Quantity (Pkg)',
        digits=(16, 3),
        required=True,
        help='Quantity in packages for this lot'
    )
    
    quantity_units = fields.Float(
        string='Quantity (Units)',
        compute='_compute_quantity_units',
        store=True,
        digits=(16, 3),
        help='Quantity in units (reference only)'
    )
    
    # ========================================================================
    # DATES
    # ========================================================================
    
    production_date = fields.Date(
        string='Production Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
        help='Date this lot was produced'
    )
    
    expiry_date = fields.Date(
        string='Expiry Date',
        tracking=True,
        help='Expiry date for this lot (calculated from production date + product shelf life)'
    )
    
    days_to_expiry = fields.Integer(
        string='Days to Expiry',
        compute='_compute_days_to_expiry',
        help='Days remaining until expiry'
    )
    
    is_expired = fields.Boolean(
        string='Expired',
        compute='_compute_days_to_expiry',
        help='True if lot has expired'
    )
    
    # ========================================================================
    # NOTES
    # ========================================================================
    
    notes = fields.Text(
        string='Lot Notes',
        help='Additional notes about this lot'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('quantity', 'product_packaging_id.qty')
    def _compute_quantity_units(self):
        """Convert package quantity to units"""
        for lot in self:
            lot.quantity_units = lot.quantity * lot.packaging_qty
    
    @api.depends('expiry_date')
    def _compute_days_to_expiry(self):
        """Calculate days remaining to expiry"""
        today = fields.Date.today()
        for lot in self:
            if lot.expiry_date:
                delta = lot.expiry_date - today
                lot.days_to_expiry = delta.days
                lot.is_expired = delta.days < 0
            else:
                lot.days_to_expiry = 0
                lot.is_expired = False
    
    @api.onchange('production_date', 'product_id')
    def _onchange_production_date(self):
        """Auto-calculate expiry date from production date + product shelf life"""
        for lot in self:
            if lot.production_date and lot.product_id:
                product_tmpl = lot.product_id.product_tmpl_id
                if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                    lot.expiry_date = lot.production_date + timedelta(days=product_tmpl.production_to_expiry_days)
                else:
                    lot.expiry_date = False
    
    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    @api.constrains('production_date', 'expiry_date')
    def _check_expiry_after_production(self):
        """Expiry date must be after production date"""
        for lot in self:
            if lot.production_date and lot.expiry_date:
                if lot.expiry_date < lot.production_date:
                    raise ValidationError(_(
                        'Expiry date (%s) cannot be earlier than production date (%s) for lot %s'
                    ) % (lot.expiry_date, lot.production_date, lot.lot_number))
    
    @api.constrains('lot_number', 'product_id')
    def _check_unique_lot_number(self):
        """Lot number should be unique per product (warning only in log)"""
        for lot in self:
            if lot.lot_number and lot.product_id:
                duplicate = self.search([
                    ('id', '!=', lot.id),
                    ('product_id', '=', lot.product_id.id),
                    ('lot_number', '=', lot.lot_number)
                ], limit=1)
                if duplicate:
                    _logger.warning(
                        'Duplicate lot number %s for product %s (Lot IDs: %s, %s)',
                        lot.lot_number, lot.product_id.name, lot.id, duplicate.id
                    )
    
    @api.constrains('quantity')
    def _check_quantity_positive(self):
        """Quantity must be positive"""
        for lot in self:
            if lot.quantity <= 0:
                raise ValidationError(_(
                    'Lot quantity must be positive. Got: %.3f'
                ) % lot.quantity)
    
    # ========================================================================
    # DISPLAY
    # ========================================================================
    
    def name_get(self):
        result = []
        for lot in self:
            name = f"{lot.lot_number} ({lot.quantity:.2f} pkg)"
            if lot.production_date:
                name += f" - Prod: {lot.production_date}"
            result.append((lot.id, name))
        return result
    
    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        """Enable search by lot number"""
        args = args or []
        if name:
            args = ['|', ('lot_number', operator, name), ('notes', operator, name)] + args
        return self._search(args, limit=limit, access_rights_uid=name_get_uid)