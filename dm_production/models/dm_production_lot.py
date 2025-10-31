# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmProductionLot(models.Model):
    _name = 'dm.production.lot'
    _description = 'Production Lot Detail'
    _order = 'production_line_id, sequence, id'
    
    # ========================================================================
    # HEADER
    # ========================================================================
    
    production_line_id = fields.Many2one(
        'dm.production.line',
        string='Production Line',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    production_run_id = fields.Many2one(
        'dm.production.run',
        related='production_line_id.production_run_id',
        string='Production Run',
        store=True,
        readonly=True,
        index=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    state = fields.Selection(
        related='production_run_id.state',
        string='PR State',
        store=True,
        readonly=True
    )
    
    # ========================================================================
    # PRODUCT INFO (RELATED)
    # ========================================================================
    
    product_id = fields.Many2one(
        'product.product',
        related='production_line_id.product_id',
        string='Product',
        store=True,
        readonly=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        related='production_line_id.product_packaging_id',
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
        help='Date this lot was produced'
    )
    
    expiry_date = fields.Date(
        string='Expiry Date',
        help='Expiry date for this lot (calculated from production date + product shelf life)'
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
    
    # ========================================================================
    # DISPLAY
    # ========================================================================
    
    def name_get(self):
        result = []
        for lot in self:
            name = f"{lot.lot_number} ({lot.quantity:.2f} pkg)"
            result.append((lot.id, name))
        return result