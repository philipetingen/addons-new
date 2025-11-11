# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class DmDeal(models.Model):
    """
    Extend dm.deal with shipment-specific fields and methods
    
    Phase 5 Sprint 1: Refactored to use indirect allocation via Production Runs
    - shipment_allocated: Computed from PR allocation status
    - shipment_ids: Collected from PRs (indirect relationship)
    - Old direct allocation deprecated with warning
    """
    _inherit = 'dm.deal'
    
    # ========================================================================
    # SHIPMENT ALLOCATION STATUS (INDIRECT VIA PRs)
    # ========================================================================
    
    shipment_allocated = fields.Boolean(
        compute='_compute_shipment_allocated',
        store=False,  # ← KEY CHANGE - compute on-demand only
        string='Allocated to Shipment',
    )

    shipment_allocation_status = fields.Selection([
        ('not_allocated', 'Not Allocated'),
        ('partial', 'Partially Allocated'),
        ('allocated', 'Fully Allocated'),
    ], compute='_compute_shipment_allocated',
       store=False,  # ← KEY CHANGE
       string='Shipment Status',
    )

    shipment_ids = fields.Many2many(
        'dm.shipment',
        compute='_compute_shipments',
        store=False,  # Already not stored
        string='Shipments',
    )

    shipment_count = fields.Integer(
        compute='_compute_shipment_count',
        store=False,  # Already not stored
        string='Shipment Count'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('production_run_ids')
    def _compute_shipment_allocated(self):
        """
        Compute shipment allocation status indirectly through production runs.
        
        Logic:
        - not_allocated: No PRs OR no PRs allocated to shipments
        - allocated: All PRs allocated to shipments
        - partial: Some PRs allocated to shipments
        """
        for deal in self:
            # Check if production module is installed
            if 'dm.production.run' not in self.env or not hasattr(deal, 'production_run_ids'):
                deal.shipment_allocated = False
                deal.shipment_allocation_status = 'not_allocated'
                continue
            
            prs = deal.production_run_ids
            
            if not prs:
                deal.shipment_allocated = False
                deal.shipment_allocation_status = 'not_allocated'
                continue
            
            # Count allocated PRs - check if field exists in model definition
            if 'shipment_allocated' not in self.env['dm.production.run']._fields:
                deal.shipment_allocated = False
                deal.shipment_allocation_status = 'not_allocated'
                continue
            
            try:
                allocated_prs = prs.filtered(lambda pr: pr.shipment_allocated)
            except Exception as e:
                _logger.debug(f"Could not check PR shipment allocation for deal {deal.name}: {e}")
                deal.shipment_allocated = False
                deal.shipment_allocation_status = 'not_allocated'
                continue
            
            if not allocated_prs:
                deal.shipment_allocated = False
                deal.shipment_allocation_status = 'not_allocated'
            elif len(allocated_prs) == len(prs):
                deal.shipment_allocated = True
                deal.shipment_allocation_status = 'allocated'
            else:
                deal.shipment_allocated = True
                deal.shipment_allocation_status = 'partial'
    
    @api.depends('production_run_ids')
    def _compute_shipments(self):
        """
        Get shipments indirectly through production runs.
        
        Collects unique shipments from all PRs allocated to this deal.
        """
        for deal in self:
            shipments = self.env['dm.shipment']
            
            # Check if production module is installed
            if 'dm.production.run' not in self.env or not hasattr(deal, 'production_run_ids'):
                deal.shipment_ids = shipments
                continue
            
            # Check if shipment model exists
            if 'dm.shipment' not in self.env:
                deal.shipment_ids = shipments
                continue
            
            # Check if production run has shipment_ids field
            if 'shipment_ids' not in self.env['dm.production.run']._fields:
                deal.shipment_ids = shipments
                continue
            
            # Safely collect shipments from PRs
            try:
                for pr in deal.production_run_ids:
                    # Use _fields check instead of hasattr to avoid triggering compute
                    try:
                        pr_shipments = pr.shipment_ids
                        if pr_shipments:
                            shipments |= pr_shipments
                    except Exception as e:
                        _logger.debug(f"Could not access shipments for PR {pr.name}: {e}")
                        continue
            except Exception as e:
                _logger.debug(f"Could not compute shipments for deal {deal.name}: {e}")
            
            deal.shipment_ids = shipments
    
    @api.depends('shipment_ids')
    def _compute_shipment_count(self):
        """Count unique shipments"""
        for deal in self:
            try:
                deal.shipment_count = len(deal.shipment_ids)
            except Exception:
                deal.shipment_count = 0
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_allocate_to_shipment(self):
        """
        DEPRECATED: Direct deal-to-shipment allocation.
        
        Phase 5 Sprint 1: Show warning, redirect to PR allocation.
        Sprint 2+: Method will be disabled completely.
        """
        self.ensure_one()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Feature Changed'),
                'message': _(
                    'Shipment allocation has moved to Production Runs.\n\n'
                    'Please allocate Production Runs to shipments instead:\n'
                    '1. Open the Production Run\n'
                    '2. Click "Allocate to Shipment" button\n\n'
                    'This provides better validation and traceability.'
                ),
                'type': 'warning',
                'sticky': True,
            }
        }
    
    def action_view_shipments(self):
        """View shipments for this deal (via production runs)"""
        self.ensure_one()
        
        if not self.shipment_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('No shipments found for this deal.'),
                    'type': 'info',
                }
            }
        
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
        
        return action# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class DmDeal(models.Model):
    """
    Extend dm.deal with shipment-specific fields and methods
    
    Phase 5 Sprint 1: Refactored to use indirect allocation via Production Runs
    - shipment_allocated: Computed from PR allocation status
    - shipment_ids: Collected from PRs (indirect relationship)
    - Old direct allocation deprecated with warning
    """
    _inherit = 'dm.deal'
    
    # ========================================================================
    # SHIPMENT ALLOCATION STATUS (INDIRECT VIA PRs)
    # ========================================================================
    
    shipment_allocated = fields.Boolean(
        compute='_compute_shipment_allocated',
        store=True,
        string='Allocated to Shipment',
        help='True if any production run is allocated to shipment'
    )
    
    shipment_allocation_status = fields.Selection([
        ('not_allocated', 'Not Allocated'),
        ('partial', 'Partially Allocated'),
        ('allocated', 'Fully Allocated'),
    ], compute='_compute_shipment_allocated',
       store=True,
       string='Shipment Status',
       help='Allocation status based on production runs'
    )
    
    shipment_ids = fields.Many2many(
        'dm.shipment',
        compute='_compute_shipments',
        string='Shipments',
        help='Shipments linked via production runs'
    )
    
    shipment_count = fields.Integer(
        compute='_compute_shipment_count',
        string='Shipment Count'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('production_run_ids')
    def _compute_shipment_allocated(self):
        """Compute shipment allocation - ULTRA DEFENSIVE"""
        for deal in self:
            try:
                # Default values
                deal.shipment_allocated = False
                deal.shipment_allocation_status = 'not_allocated'
                
                # Safety checks
                if 'dm.production.run' not in self.env:
                    continue
                if not hasattr(deal, 'production_run_ids'):
                    continue
                
                prs = deal.production_run_ids
                if not prs:
                    continue
                
                # Check if shipment_allocated field exists on PR
                if 'shipment_allocated' not in self.env['dm.production.run']._fields:
                    continue
                
                # Count allocated PRs
                allocated_count = 0
                for pr in prs:
                    try:
                        if pr.shipment_allocated:
                            allocated_count += 1
                    except Exception:
                        continue
                
                # Set values
                if allocated_count > 0:
                    deal.shipment_allocated = True
                    if allocated_count == len(prs):
                        deal.shipment_allocation_status = 'allocated'
                    else:
                        deal.shipment_allocation_status = 'partial'
                        
            except Exception as e:
                # Silent fail - just use defaults
                _logger.debug(f"Could not compute shipment status for deal {deal.id}: {e}")
                deal.shipment_allocated = False
                deal.shipment_allocation_status = 'not_allocated'

    @api.depends('production_run_ids')
    def _compute_shipments(self):
        """Get shipments from PRs - ULTRA DEFENSIVE"""
        for deal in self:
            try:
                shipments = self.env['dm.shipment']
                
                # Safety checks
                if 'dm.production.run' not in self.env:
                    deal.shipment_ids = shipments
                    continue
                if not hasattr(deal, 'production_run_ids'):
                    deal.shipment_ids = shipments
                    continue
                if 'dm.shipment' not in self.env:
                    deal.shipment_ids = shipments
                    continue
                if 'shipment_ids' not in self.env['dm.production.run']._fields:
                    deal.shipment_ids = shipments
                    continue
                
                # Collect shipments
                for pr in deal.production_run_ids:
                    try:
                        shipments |= pr.shipment_ids
                    except Exception:
                        continue
                
                deal.shipment_ids = shipments
                
            except Exception as e:
                _logger.debug(f"Could not compute shipments for deal {deal.id}: {e}")
                deal.shipment_ids = self.env['dm.shipment']

    @api.depends('shipment_ids')
    def _compute_shipment_count(self):
        """Count shipments - ULTRA DEFENSIVE"""
        for deal in self:
            try:
                deal.shipment_count = len(deal.shipment_ids)
            except Exception:
                deal.shipment_count = 0
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_allocate_to_shipment(self):
        """
        DEPRECATED: Direct deal-to-shipment allocation.
        
        Phase 5 Sprint 1: Show warning, redirect to PR allocation.
        Sprint 2+: Method will be disabled completely.
        """
        self.ensure_one()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Feature Changed'),
                'message': _(
                    'Shipment allocation has moved to Production Runs.\n\n'
                    'Please allocate Production Runs to shipments instead:\n'
                    '1. Open the Production Run\n'
                    '2. Click "Allocate to Shipment" button\n\n'
                    'This provides better validation and traceability.'
                ),
                'type': 'warning',
                'sticky': True,
            }
        }
    
    def action_view_shipments(self):
        """View shipments for this deal (via production runs)"""
        self.ensure_one()
        
        if not self.shipment_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('No shipments found for this deal.'),
                    'type': 'info',
                }
            }
        
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