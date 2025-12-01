# -*- coding: utf-8 -*-
"""
Account Move Extension
Adds DM-specific fields for invoice tracking
"""

from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    # ============================================================
    # DM REFERENCE FIELDS
    # ============================================================
    
    dm_deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        ondelete='restrict',
        index=True,
        help='Source deal for this invoice'
    )
    
    dm_shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        ondelete='restrict',
        index=True,
        help='Source shipment for this invoice'
    )
    
    is_product_invoice = fields.Boolean(
        string='Product Invoice',
        default=False,
        help='This is a product invoice (part of split invoicing)'
    )
    
    is_service_invoice = fields.Boolean(
        string='Service Invoice',
        default=False,
        help='This is a service invoice (part of split invoicing)'
    )
    
    # ============================================================
    # DOWNPAYMENT TRACKING
    # ============================================================
    
    downpayment_ids = fields.Many2many(
        'dm.downpayment.request',
        'dm_invoice_downpayment_rel',
        'invoice_id',
        'downpayment_id',
        string='Applied Downpayments',
        help='Downpayments applied to this invoice'
    )
    
    downpayment_count = fields.Integer(
        string='DP Count',
        compute='_compute_downpayment_count'
    )
    
    total_downpayment_applied = fields.Monetary(
        string='Total DP Applied',
        compute='_compute_total_downpayment_applied',
        currency_field='currency_id',
        help='Sum of all downpayments applied to this invoice'
    )
    
    # ============================================================
    # COMPUTE METHODS
    # ============================================================
    
    def _compute_downpayment_count(self):
        for move in self:
            move.downpayment_count = len(move.downpayment_ids)
    
    @api.depends('downpayment_ids.amount_received')
    def _compute_total_downpayment_applied(self):
        for move in self:
            move.total_downpayment_applied = sum(
                move.downpayment_ids.mapped('amount_received')
            )
    
    # ============================================================
    # SMART BUTTONS
    # ============================================================
    
    def action_view_downpayments(self):
        """View downpayments applied to this invoice"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Applied Downpayments'),
            'res_model': 'dm.downpayment.request',
            'domain': [('id', 'in', self.downpayment_ids.ids)],
            'view_mode': 'tree,form',
            'target': 'current',
        }
    
    def action_view_deal(self):
        """Navigate to source deal"""
        self.ensure_one()
        if not self.dm_deal_id:
            return
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deal'),
            'res_model': 'dm.deal',
            'res_id': self.dm_deal_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_shipment(self):
        """Navigate to source shipment"""
        self.ensure_one()
        if not self.dm_shipment_id:
            return
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shipment'),
            'res_model': 'dm.shipment',
            'res_id': self.dm_shipment_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class DmDeal(models.Model):
    _inherit = 'dm.deal'
    
    # Link back to invoices
    invoice_count = fields.Integer(
        string='Invoices',
        compute='_compute_invoice_count'
    )
    
    @api.depends('name')  # Simplified - just count, no relation
    def _compute_invoice_count(self):
        """Count invoices linked to this deal"""
        for deal in self:
            count = self.env['account.move'].search_count([
                ('dm_deal_id', '=', deal.id),
                ('move_type', 'in', ['out_invoice', 'out_refund'])
            ])
            deal.invoice_count = count
    
    def action_view_invoices(self):
        """View customer invoices for this deal"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Invoices'),
            'res_model': 'account.move',
            'domain': [('dm_deal_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
        }