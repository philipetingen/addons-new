# -*- coding: utf-8 -*-
"""
Production Allocation Board - Phase 3 Basic Version

Visual board for allocating unallocated deals to production runs.
Shows capacity utilization and prevents over-allocation.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProductionAllocationBoard(models.TransientModel):
    """
    Basic Allocation Board Wizard
    
    Shows unallocated deals and existing production runs
    Allows quick allocation with capacity checking
    """
    _name = 'dm.production.allocation.board'
    _description = 'Production Allocation Board'
    
    # Filters
    supplier_id = fields.Many2one(
        'res.partner',
        string='Filter by Supplier',
        domain=[('supplier_rank', '>', 0)]
    )
    
    date_from = fields.Date(
        string='RTS From',
        default=fields.Date.today
    )
    
    date_to = fields.Date(string='RTS To')
    
    # Selected deals for bulk operations
    selected_deal_ids = fields.Many2many(
        'dm.deal',
        'production_board_selected_rel',
        'board_id',
        'deal_id',
        string='Selected Deals',
        help='Deals selected for bulk allocation'
    )
    
    # Unallocated deals
    unallocated_deal_ids = fields.Many2many(
        'dm.deal',
        'production_board_unallocated_rel',
        'board_id',
        'deal_id',
        string='Unallocated Deals',
        compute='_compute_unallocated_deals'
    )
    
    unallocated_count = fields.Integer(
        compute='_compute_unallocated_count'
    )
    
    # Existing production runs
    production_run_ids = fields.Many2many(
        'dm.production.run',
        'production_board_run_rel',
        'board_id',
        'run_id',
        string='Production Runs',
        compute='_compute_production_runs'
    )
    
    production_run_count = fields.Integer(
        compute='_compute_production_run_count'
    )
    
    # Summary stats
    total_unallocated_teu = fields.Float(
        string='Total Unallocated TEU',
        compute='_compute_summary_stats'
    )
    
    selected_count = fields.Integer(
        string='Selected Deals',
        compute='_compute_selected_count'
    )
    
    selected_teu = fields.Float(
        string='Selected TEU',
        compute='_compute_selected_stats'
    )
    
    @api.depends('supplier_id', 'date_from', 'date_to')
    def _compute_unallocated_deals(self):
        """Find unallocated deals matching filters"""
        for board in self:
            domain = [
                ('production_allocated', '=', False),
                ('state', 'in', ['confirmed', 'ready']),  # Only confirmed deals
            ]
            
            if board.supplier_id:
                domain.append(('supplier_id', '=', board.supplier_id.id))
            
            if board.date_from:
                domain.append(('rts_current', '>=', board.date_from))
            
            if board.date_to:
                domain.append(('rts_current', '<=', board.date_to))
            
            board.unallocated_deal_ids = self.env['dm.deal'].search(domain, order='rts_current, supplier_id')
    
    @api.depends('unallocated_deal_ids')
    def _compute_unallocated_count(self):
        for board in self:
            board.unallocated_count = len(board.unallocated_deal_ids)
    
    @api.depends('selected_deal_ids')
    def _compute_selected_count(self):
        for board in self:
            board.selected_count = len(board.selected_deal_ids)
    
    @api.depends('selected_deal_ids', 'selected_deal_ids.total_teu')
    def _compute_selected_stats(self):
        for board in self:
            total_teu = sum(
                d.total_teu if hasattr(d, 'total_teu') else 0 
                for d in board.selected_deal_ids
            )
            board.selected_teu = total_teu
    
    @api.depends('supplier_id', 'date_from', 'date_to')
    def _compute_production_runs(self):
        """Find production runs matching filters"""
        for board in self:
            domain = [
                ('state', 'in', ['draft', 'confirmed']),  # Only active planning runs
            ]
            
            if board.supplier_id:
                domain.append(('supplier_id', '=', board.supplier_id.id))
            
            if board.date_from:
                domain.append(('rts_date', '>=', board.date_from))
            
            if board.date_to:
                domain.append(('rts_date', '<=', board.date_to))
            
            board.production_run_ids = self.env['dm.production.run'].search(
                domain, 
                order='rts_date, supplier_id'
            )
    
    @api.depends('production_run_ids')
    def _compute_production_run_count(self):
        for board in self:
            board.production_run_count = len(board.production_run_ids)
    
    @api.depends('unallocated_deal_ids', 'unallocated_deal_ids.total_teu')
    def _compute_summary_stats(self):
        for board in self:
            total_teu = sum(
                d.total_teu if hasattr(d, 'total_teu') else 0 
                for d in board.unallocated_deal_ids
            )
            board.total_unallocated_teu = total_teu
    
    def action_refresh(self):
        """Refresh the board by recomputing all fields"""
        self.ensure_one()
        # Trigger recomputation of computed fields
        self._compute_unallocated_deals()
        self._compute_production_runs()
        self._compute_summary_stats()
        # Return True to stay on same page (don't open new window)
        return True
    
    def action_select_deal(self):
        """Add deal to selection"""
        self.ensure_one()
        deal_id = self.env.context.get('deal_to_select')
        if deal_id:
            self.selected_deal_ids = [(4, deal_id)]  # Add to many2many
        return {'type': 'ir.actions.act_window_close'}
    
    def action_unselect_deal(self):
        """Remove deal from selection"""
        self.ensure_one()
        deal_id = self.env.context.get('deal_to_unselect')
        if deal_id:
            self.selected_deal_ids = [(3, deal_id)]  # Remove from many2many
        return {'type': 'ir.actions.act_window_close'}
    
    def action_create_production_run(self):
        """Create new production run from selected deals"""
        self.ensure_one()
        
        context = {}
        
        # If deals are selected, pre-fill PR with their data
        if self.selected_deal_ids:
            deals = self.selected_deal_ids
            
            # Get common supplier (should be same for all selected deals)
            suppliers = deals.mapped('supplier_id')
            if len(suppliers) == 1:
                context['default_supplier_id'] = suppliers[0].id
            elif len(suppliers) > 1:
                # Warning: multiple suppliers selected
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Multiple Suppliers'),
                        'message': _('Selected deals have different suppliers. Please select deals from one supplier only.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            
            # Get max RTS date from selected deals
            rts_dates = [d.rts_current for d in deals if hasattr(d, 'rts_current') and d.rts_current]
            if rts_dates:
                context['default_rts_date'] = max(rts_dates)
            
            # Store selected deal IDs for allocation after PR creation
            context['default_deal_ids_to_allocate'] = deals.ids
        else:
            # No deals selected, use filter
            if self.supplier_id:
                context['default_supplier_id'] = self.supplier_id.id
            if self.date_from:
                context['default_rts_date'] = self.date_from
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Production Run'),
            'res_model': 'dm.production.run',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }
    
    def action_quick_allocate_deal(self):
        """
        Open quick allocate wizard for a specific deal
        Called from tree view button with deal_id in context
        """
        self.ensure_one()
        deal_id = self.env.context.get('deal_id')
        
        if not deal_id:
            raise UserError(_('No deal specified for allocation'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quick Allocate Deal'),
            'res_model': 'dm.production.quick.allocate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_deal_id': deal_id,
            }
        }