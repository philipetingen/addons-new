# -*- coding: utf-8 -*-
from odoo import api, fields, models

class DmDealTotals(models.Model):
    """Extend dm.deal with loaded quantity totals
    
    Must load AFTER dm_deal_line_quantities.py so fields exist.
    """
    _inherit = 'dm.deal'
    
    # ============================================================
    # CONTRACTED AMOUNTS - Use existing fields, just update computation
    # ============================================================
    # Fields amount_untaxed_sale and amount_untaxed_purchase already exist in dm_deal.py
    # We just need to ensure _compute_totals uses the right source
    
    # ============================================================
    # CONTRACTED MARGIN (NEW - doesn't conflict)
    # ============================================================
    
    margin_contracted = fields.Monetary(
        string='Margin (Contracted)',
        compute='_compute_contracted_margin',
        store=True,
        currency_field='currency_id',
    )
    
    margin_contracted_percent = fields.Float(
        string='Margin % (Contracted)',
        compute='_compute_contracted_margin',
        store=True,
    )
    
    @api.depends('amount_untaxed_sale', 'amount_untaxed_purchase')
    def _compute_contracted_margin(self):
        for deal in self:
            deal.margin_contracted = deal.amount_untaxed_sale - deal.amount_untaxed_purchase
            
            if deal.amount_untaxed_sale > 0:
                deal.margin_contracted_percent = (deal.margin_contracted / deal.amount_untaxed_sale) * 100
            else:
                deal.margin_contracted_percent = 0.0
    
    # ============================================================
    # LOADED AMOUNTS (Based on Loaded Quantities)
    # ============================================================
    
    total_loaded_sale = fields.Float(
        string='Total Loaded (Sale)',
        compute='_compute_loaded_totals',
        store=True,
    )
    
    total_loaded_purchase = fields.Float(
        string='Total Loaded (Purchase)',
        compute='_compute_loaded_totals',
        store=True,
    )
    
    margin_loaded = fields.Float(
        string='Margin (Loaded)',
        compute='_compute_loaded_totals',
        store=True,
    )
    
    margin_loaded_percent = fields.Float(
        string='Margin % (Loaded)',
        compute='_compute_loaded_totals',
        store=True,
    )
    
    @api.depends('line_ids.amount_loaded_sale', 'line_ids.amount_loaded_purchase')
    def _compute_loaded_totals(self):
        for deal in self:
            deal.total_loaded_sale = sum(deal.line_ids.mapped('amount_loaded_sale'))
            deal.total_loaded_purchase = sum(deal.line_ids.mapped('amount_loaded_purchase'))
            deal.margin_loaded = deal.total_loaded_sale - deal.total_loaded_purchase
            
            if deal.total_loaded_sale > 0:
                deal.margin_loaded_percent = (deal.margin_loaded / deal.total_loaded_sale) * 100
            else:
                deal.margin_loaded_percent = 0.0
    
    # ============================================================
    # LOT TRACKING SUMMARY
    # ============================================================
    
    total_lot_count = fields.Integer(
        string='Total Lots',
        compute='_compute_lot_summary',
        store=True,
    )
    
    lines_with_lots = fields.Integer(
        string='Lines with Lots',
        compute='_compute_lot_summary',
        store=True,
    )
    
    all_lines_lotted = fields.Boolean(
        string='All Lines Lotted',
        compute='_compute_lot_summary',
        store=True,
    )
    
    @api.depends('line_ids.lot_ids', 'line_ids.lot_count', 'line_ids.quantity_loaded')
    def _compute_lot_summary(self):
        """Compute lot tracking summary - uses ONLY lot_ids (single source of truth)"""
        for deal in self:
            # Total lots across all lines (from One2many records only)
            deal.total_lot_count = sum(deal.line_ids.mapped('lot_count'))
            
            # Lines that have lot records
            lines_with_lot_data = deal.line_ids.filtered(lambda l: l.lot_ids)
            deal.lines_with_lots = len(lines_with_lot_data)
            
            # Check if all loaded lines have lot tracking
            loaded_lines = deal.line_ids.filtered(lambda l: l.quantity_loaded > 0)
            if loaded_lines:
                lotted_loaded_lines = loaded_lines.filtered(lambda l: l.lot_ids)
                deal.all_lines_lotted = len(lotted_loaded_lines) == len(loaded_lines)
            else:
                deal.all_lines_lotted = False