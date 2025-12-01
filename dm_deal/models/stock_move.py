# -*- coding: utf-8 -*-
from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    """
    DonnaMello Stock Move Extensions
    
    Package-Native: Carries actual loaded package qty and deal price
    through inventory operations for invoice chain.
    """
    _inherit = 'stock.move'
    
    dm_deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        readonly=True,
        index=True,
        help='Reference to originating deal line'
    )
    
    packaging_qty_dm = fields.Float(
        string='Pkg Qty (DM)',
        digits=(16, 3),
        readonly=True,
        help='Actual loaded quantity in packages - from deal line quantity_loaded'
    )
    
    packaging_price_unit = fields.Float(
        string='Pkg Price',
        digits=(16, 6),
        readonly=True,
        help='Price per package from deal - for invoice chain'
    )
    
    is_dm_move = fields.Boolean(
        string='Is DM Move',
        compute='_compute_is_dm_move',
        store=True,
        help='True if this move originated from a DM deal'
    )
    
    @api.depends('dm_deal_line_id')
    def _compute_is_dm_move(self):
        for move in self:
            move.is_dm_move = bool(move.dm_deal_line_id)


class StockMoveLine(models.Model):
    """
    DonnaMello Stock Move Line Extensions
    
    Carries package-native fields from parent move for lot/serial tracking.
    """
    _inherit = 'stock.move.line'
    
    dm_deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        related='move_id.dm_deal_line_id',
        store=True,
        readonly=True,
        help='Reference to originating deal line'
    )
    
    packaging_qty_dm = fields.Float(
        string='Pkg Qty (DM)',
        related='move_id.packaging_qty_dm',
        store=True,
        readonly=True,
        help='Actual loaded quantity in packages from parent move'
    )
    
    packaging_price_unit = fields.Float(
        string='Pkg Price',
        related='move_id.packaging_price_unit',
        store=True,
        readonly=True,
        help='Price per package from parent move'
    )
    
    is_dm_move_line = fields.Boolean(
        string='Is DM Move Line',
        related='move_id.is_dm_move',
        store=True,
        readonly=True
    )