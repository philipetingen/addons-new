# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmProductionRun(models.Model):
    """
    Extend dm.production.run with shipment allocation capabilities
    
    Phase 5 Sprint 1: PR-level shipment allocation
    This module extends production runs when dm_shipment is installed.
    """
    _inherit = 'dm.production.run'
    
    # ========================================================================
    # SHIPMENT ALLOCATION (PHASE 5 SPRINT 1)
    # ========================================================================
    
    shipment_ids = fields.Many2many(
        'dm.shipment',
        'dm_production_shipment_rel',
        'production_run_id',
        'shipment_id',
        string='Shipments',
        help='Shipments this PR is allocated to'
    )
    
    shipment_allocated = fields.Boolean(
        compute='_compute_shipment_allocated',
        store=True,
        string='Allocated to Shipment',
        help='True if this PR is allocated to at least one shipment'
    )
    
    shipment_allocation_status = fields.Selection([
        ('not_allocated', 'Not Allocated'),
        ('partial', 'Partially Allocated'),
        ('allocated', 'Fully Allocated'),
    ], compute='_compute_shipment_allocated',
       store=True,
       string='Shipment Status',
       help='Allocation status based on line-level tracking'
    )
    
    shipment_count = fields.Integer(
        compute='_compute_shipment_count',
        string='Shipment Count'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('shipment_ids')
    def _compute_shipment_count(self):
        """Count allocated shipments"""
        for pr in self:
            pr.shipment_count = len(pr.shipment_ids)
    
    @api.depends('shipment_ids')
    def _compute_shipment_allocated(self):
        """
        Compute allocation status.
        
        Sprint 1: Simple presence check
        Sprint 2: Will check line_ids.shipment_allocation_status
        """
        for pr in self:
            if not pr.shipment_ids:
                pr.shipment_allocated = False
                pr.shipment_allocation_status = 'not_allocated'
            else:
                pr.shipment_allocated = True
                pr.shipment_allocation_status = 'allocated'
    
    # ========================================================================
    # SHIPMENT ALLOCATION ACTIONS
    # ========================================================================
    
    def action_allocate_to_shipment(self):
        """
        Open shipment allocation wizard for this PR.
        
        Validates:
        - PR must be in 'ready' or 'completed' state
        - PR must not be cancelled
        """
        self.ensure_one()
        
        if self.state not in ['ready', 'completed']:
            raise UserError(_(
                'Production Run must be in "Ready to Ship" or "Completed" state '
                'before allocation to shipment.\n\n'
                'Current state: %s'
            ) % dict(self._fields['state'].selection).get(self.state))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Allocate to Shipment'),
            'res_model': 'dm.shipment.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_production_run_ids': [(6, 0, self.ids)],
                'default_shipment_mode': 'new',
            },
        }
    
    def action_view_shipments(self):
        """View allocated shipments"""
        self.ensure_one()
        
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Shipments'),
            'res_model': 'dm.shipment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.shipment_ids.ids)],
            'context': self.env.context,
        }
        
        if len(self.shipment_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.shipment_ids.id
        
        return action