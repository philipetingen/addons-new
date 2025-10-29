# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    """Extend partner to add capacity management"""
    _inherit = 'res.partner'
    
    # Capacity records for this vendor
    vendor_capacity_ids = fields.One2many(
        'dm.vendor.capacity',
        'vendor_id',
        string='Production Capacity',
        help='Time-based production capacity records'
    )
    
    # Current capacity
    current_capacity_id = fields.Many2one(
        'dm.vendor.capacity',
        compute='_compute_current_capacity',
        string='Current Capacity',
        help='Currently active capacity record'
    )
    
    current_capacity_teu = fields.Float(
        related='current_capacity_id.effective_capacity_teu',
        string='Current Capacity (TEU/Month)',
        readonly=True
    )
    
    has_capacity_configured = fields.Boolean(
        compute='_compute_has_capacity_configured',
        string='Has Capacity',
        help='True if vendor has at least one capacity record'
    )
    
    capacity_count = fields.Integer(
        compute='_compute_capacity_count',
        string='# Capacity Records'
    )
    
    @api.depends('vendor_capacity_ids', 'vendor_capacity_ids.is_current', 'vendor_capacity_ids.active')
    def _compute_current_capacity(self):
        """Get currently active capacity record"""
        for partner in self:
            current = partner.vendor_capacity_ids.filtered(
                lambda c: c.is_current and c.active
            )
            partner.current_capacity_id = current[:1] if current else False
    
    @api.depends('vendor_capacity_ids')
    def _compute_has_capacity_configured(self):
        """Check if vendor has any capacity configured"""
        for partner in self:
            partner.has_capacity_configured = bool(partner.vendor_capacity_ids)
    
    @api.depends('vendor_capacity_ids')
    def _compute_capacity_count(self):
        """Count capacity records"""
        for partner in self:
            partner.capacity_count = len(partner.vendor_capacity_ids)
    
    def action_view_capacity_records(self):
        """Open capacity records for this vendor"""
        self.ensure_one()
        return {
            'name': _('Production Capacity: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'dm.vendor.capacity',
            'view_mode': 'tree,form',
            'domain': [('vendor_id', '=', self.id)],
            'context': {'default_vendor_id': self.id},
        }