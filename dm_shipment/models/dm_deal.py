# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class DmDeal(models.Model):
    """
    Extend dm.deal with shipment-specific fields and methods
    """
    _inherit = 'dm.deal'
    
    # ========================================================================
    # SHIPMENT FIELDS
    # ========================================================================
    
    shipment_allocated = fields.Boolean(
        string='Allocated to Shipment',
        compute='_compute_shipment_allocated',
        store=True,
        help='Deal is allocated to at least one active shipment'
    )
    
    shipment_ids = fields.Many2many(
        'dm.shipment',
        compute='_compute_shipments',
        string='Shipments',
        help='Shipments this deal is allocated to'
    )
    
    shipment_count = fields.Integer(
        compute='_compute_shipment_count',
        string='Shipment Count'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('allocation_ids', 'allocation_ids.state', 'allocation_ids.allocation_type')
    def _compute_shipment_allocated(self):
        """Check if deal has active or completed shipment allocation"""
        for deal in self:
            deal.shipment_allocated = any(
                a.allocation_type == 'shipment' and a.state in ['active', 'completed']
                for a in deal.allocation_ids
            )
    
    @api.depends('allocation_ids', 'allocation_ids.shipment_id')
    def _compute_shipments(self):
        """Get shipments from allocations"""
        for deal in self:
            ship_allocations = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'shipment' 
                and a.state in ['active', 'completed']
                and a.shipment_id
            )
            deal.shipment_ids = ship_allocations.mapped('shipment_id')
    
    @api.depends('shipment_ids')
    def _compute_shipment_count(self):
        for deal in self:
            deal.shipment_count = len(deal.shipment_ids)
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_allocate_to_shipment(self):
        """Open shipment allocation wizard"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Allocate to Shipment'),
            'res_model': 'dm.shipment.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_deal_ids': [(6, 0, self.ids)],
            },
        }
    
    def action_view_shipments(self):
        """View shipments for this deal"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shipments'),
            'res_model': 'dm.shipment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.shipment_ids.ids)],
            'context': self.env.context,
        }