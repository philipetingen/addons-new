# -*- coding: utf-8 -*-
from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """
    DonnaMello Account Move Extensions
    
    Links invoices/bills to deals for reporting.
    """
    _inherit = 'account.move'
    
    dm_deal_id = fields.Many2one(
        'dm.deal',
        string='DM Deal',
        readonly=True,
        index=True,
        compute='_compute_dm_deal_id',
        store=True,
        help='Reference to originating DonnaMello deal'
    )
    
    is_dm_invoice = fields.Boolean(
        string='Is DM Invoice',
        compute='_compute_is_dm_invoice',
        store=True,
        help='True if this invoice originated from a DM deal'
    )
    
    @api.depends('invoice_line_ids.dm_deal_line_id')
    def _compute_dm_deal_id(self):
        for move in self:
            deal_lines = move.invoice_line_ids.mapped('dm_deal_line_id')
            if deal_lines:
                move.dm_deal_id = deal_lines[0].deal_id
            else:
                move.dm_deal_id = False
    
    @api.depends('dm_deal_id')
    def _compute_is_dm_invoice(self):
        for move in self:
            move.is_dm_invoice = bool(move.dm_deal_id)
    
    def _get_dm_package_native_totals(self):
        """
        Calculate package-native totals for DM invoices.
        
        Returns:
            tuple: (amount_untaxed, amount_tax, amount_total)
        """
        self.ensure_one()
        amount_untaxed = 0.0
        amount_tax = 0.0
        
        for line in self.invoice_line_ids.filtered(lambda x: not x.display_type):
            if line.is_dm_line and line.packaging_qty_dm and line.packaging_price_unit:
                line_subtotal = line.packaging_qty_dm * line.packaging_price_unit
                amount_untaxed += line_subtotal
                amount_tax += line.price_total - line.price_subtotal
            else:
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_total - line.price_subtotal
        
        return amount_untaxed, amount_tax, amount_untaxed + amount_tax


class AccountMoveLine(models.Model):
    """
    DonnaMello Account Move Line Extensions
    
    Package-Native Architecture:
    - packaging_qty_dm: Quantity in packages (SOURCE OF TRUTH)
    - packaging_price_unit: Price per package with 6-decimal precision (SOURCE OF TRUTH)
    """
    _inherit = 'account.move.line'
    
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
        help='Package quantity from deal - SOURCE OF TRUTH for DM deals'
    )
    
    packaging_price_unit = fields.Float(
        string='Pkg Price',
        digits=(16, 6),
        help='Price per package with 6-decimal precision - SOURCE OF TRUTH for DM deals'
    )
    
    is_dm_line = fields.Boolean(
        string='Is DM Line',
        compute='_compute_is_dm_line',
        store=True,
        help='True if this line originated from a DM deal'
    )
    
    amount_package_native = fields.Monetary(
        string='Amount (Pkg Native)',
        compute='_compute_amount_package_native',
        store=True,
        currency_field='currency_id',
        help='Subtotal calculated from package qty × package price'
    )
    
    @api.depends('dm_deal_line_id')
    def _compute_is_dm_line(self):
        for line in self:
            line.is_dm_line = bool(line.dm_deal_line_id)
    
    @api.depends('packaging_qty_dm', 'packaging_price_unit', 'is_dm_line')
    def _compute_amount_package_native(self):
        for line in self:
            if line.is_dm_line and line.packaging_qty_dm and line.packaging_price_unit:
                line.amount_package_native = line.packaging_qty_dm * line.packaging_price_unit
            else:
                line.amount_package_native = 0.0