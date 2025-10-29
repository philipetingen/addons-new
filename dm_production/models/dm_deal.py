# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class DmDeal(models.Model):
    """
    Extend dm.deal with production-specific fields and methods
    
    Phase 3A Enhancement:
    - Quick allocation action (single deal)
    - Remove from production action
    """
    _inherit = 'dm.deal'
    
    # ========================================================================
    # PRODUCTION FIELDS
    # ========================================================================
    
    production_allocated = fields.Boolean(
        string='Allocated to Production',
        compute='_compute_production_allocated',
        store=True,
        help='Deal is allocated to at least one active production run'
    )
    
    production_run_ids = fields.Many2many(
        'dm.production.run',
        compute='_compute_production_runs',
        string='Production Runs',
        help='Production runs this deal is allocated to'
    )
    
    production_count = fields.Integer(
        compute='_compute_production_count',
        string='Production Count'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('allocation_ids', 'allocation_ids.state', 'allocation_ids.allocation_type')
    def _compute_production_allocated(self):
        """Check if deal has active or completed production allocation"""
        for deal in self:
            deal.production_allocated = any(
                a.allocation_type == 'production' and a.state in ['active', 'completed']
                for a in deal.allocation_ids
            )
    
    @api.depends('allocation_ids', 'allocation_ids.production_run_id')
    def _compute_production_runs(self):
        """Get production runs from allocations"""
        for deal in self:
            pr_allocations = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'production' 
                and a.state in ['active', 'completed']
                and a.production_run_id
            )
            deal.production_run_ids = pr_allocations.mapped('production_run_id')
    
    @api.depends('production_run_ids')
    def _compute_production_count(self):
        for deal in self:
            deal.production_count = len(deal.production_run_ids)
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_allocate_to_production(self):
        """
        Open bulk production allocation wizard
        Used for multi-deal allocation
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Allocate to Production'),
            'res_model': 'dm.production.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_deal_ids': [(6, 0, self.ids)],
            },
        }
    
    def action_quick_allocate_to_pr(self):
        """
        Phase 3A NEW: Quick allocation wizard
        Shows available PRs with capacity preview for single deal
        """
        self.ensure_one()
        
        # Check if already allocated
        if self.production_allocated:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Already Allocated'),
                    'message': _('Deal %s is already allocated to production run: %s') % (
                        self.name,
                        ', '.join(self.production_run_ids.mapped('name'))
                    ),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quick Allocate: %s') % self.name,
            'res_model': 'dm.production.quick.allocate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_deal_id': self.id,
                'default_supplier_id': self.supplier_id.id if self.supplier_id else False,
            },
        }
    
    def action_view_production_runs(self):
        """View production runs for this deal"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Runs'),
            'res_model': 'dm.production.run',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.production_run_ids.ids)],
            'context': self.env.context,
        }
    
    def action_remove_from_production(self):
        """
        Phase 3A NEW: Remove deal from production allocation
        Cancels active production allocations
        """
        self.ensure_one()
        
        if not self.production_allocated:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Not Allocated'),
                    'message': _('Deal %s is not allocated to any production run') % self.name,
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        # Find active production allocations
        active_pr_allocations = self.allocation_ids.filtered(
            lambda a: a.allocation_type == 'production' 
            and a.state == 'active'
        )
        
        if not active_pr_allocations:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Active Allocations'),
                    'message': _('Deal %s has no active production allocations to remove') % self.name,
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        # Get PR names for message
        pr_names = active_pr_allocations.mapped('production_run_id.name')
        
        # Cancel allocations
        active_pr_allocations.action_cancel()
        
        _logger.info(
            f"Removed deal {self.name} from production runs: {', '.join(pr_names)}"
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Removed from Production'),
                'message': _('Deal %s removed from: %s') % (
                    self.name,
                    ', '.join(pr_names)
                ),
                'type': 'success',
                'sticky': False,
            }
        }