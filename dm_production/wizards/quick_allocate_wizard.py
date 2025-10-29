# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProductionQuickAllocateWizard(models.TransientModel):
    """
    Quick Allocation Wizard - Phase 3A
    
    Simplified wizard for allocating a single deal to production run.
    Shows available PRs with capacity impact preview.
    
    DEFAULT MODE: Create New PR (most common real-world case)
    """
    _name = 'dm.production.quick.allocate.wizard'
    _description = 'Quick Allocate to Production'
    
    # ========================================================================
    # DEAL INFORMATION
    # ========================================================================
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        readonly=True
    )
    
    deal_name = fields.Char(
        related='deal_id.name',
        string='Deal Number',
        readonly=True
    )
    
    customer_name = fields.Char(
        related='deal_id.customer_id.name',
        string='Customer',
        readonly=True
    )
    
    supplier_id = fields.Many2one(
        related='deal_id.supplier_id',
        string='Supplier',
        readonly=True
    )
    
    rts_date = fields.Date(
        related='deal_id.rts_current',
        string='RTS Date',
        readonly=True
    )
    
    deal_teu = fields.Float(
        string='Deal TEU',
        compute='_compute_deal_teu',
        readonly=True
    )
    
    deal_containers = fields.Float(
        string='Deal Containers',
        compute='_compute_deal_info',
        readonly=True
    )
    
    product_mix = fields.Char(
        string='Product Mix',
        compute='_compute_deal_info',
        readonly=True
    )
    
    # ========================================================================
    # ALLOCATION TARGET
    # ========================================================================
    
    allocation_mode = fields.Selection([
        ('new', 'Create New Production Run'),
        ('existing', 'Allocate to Existing Production Run')
    ], string='Allocation Mode',
        default='new',  # FIXED: Most common case in real world
        required=True
    )
    
    production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        domain="[('state', 'in', ['draft', 'confirmed']), ('supplier_id', '=', supplier_id)]",
        help='Select production run to allocate to'
    )
    
    # New PR fields (if creating new)
    new_pr_rts_date = fields.Date(
        string='Target RTS Date',
        help='RTS date for new production run'
    )
    
    new_pr_production_start = fields.Date(
        string='Production Start',
        help='Production start date for new run'
    )
    
    # ========================================================================
    # CAPACITY IMPACT PREVIEW
    # ========================================================================
    
    show_capacity_warning = fields.Boolean(
        compute='_compute_capacity_impact',
        string='Has Capacity Warning'
    )
    
    capacity_warning_message = fields.Text(
        compute='_compute_capacity_impact',
        string='Capacity Warning'
    )
    
    current_pr_teu = fields.Float(
        string='Current PR TEU',
        compute='_compute_capacity_impact',
        readonly=True
    )
    
    new_pr_teu = fields.Float(
        string='After Allocation TEU',
        compute='_compute_capacity_impact',
        readonly=True
    )
    
    pr_capacity_teu = fields.Float(
        string='PR Capacity (TEU)',
        compute='_compute_capacity_impact',
        readonly=True
    )
    
    new_utilization = fields.Float(
        string='New Utilization %',
        compute='_compute_capacity_impact',
        readonly=True
    )
    
    capacity_status_color = fields.Selection([
        ('green', 'Healthy'),
        ('yellow', 'Near Limit'),
        ('red', 'Over Capacity')
    ], compute='_compute_capacity_impact', readonly=True)
    
    # ========================================================================
    # AVAILABLE PRS (for selection help)
    # ========================================================================
    
    available_pr_ids = fields.Many2many(
        'dm.production.run',
        compute='_compute_available_prs',
        string='Available Production Runs'
    )
    
    available_pr_count = fields.Integer(
        compute='_compute_available_prs',
        string='Available PRs'
    )
    
    # Helper field for showing capacity module status
    has_capacity_module = fields.Boolean(
        compute='_compute_has_capacity_module',
        string='Capacity Module Installed'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    def _compute_has_capacity_module(self):
        """Check if capacity planning module is installed"""
        for wizard in self:
            wizard.has_capacity_module = 'dm_capacity_planning' in self.env.registry._init_modules
    
    @api.depends('deal_id')
    def _compute_deal_teu(self):
        for wizard in self:
            wizard.deal_teu = wizard.deal_id.total_teu if hasattr(wizard.deal_id, 'total_teu') else 0
    
    @api.depends('deal_id', 'deal_id.line_ids')
    def _compute_deal_info(self):
        for wizard in self:
            deal = wizard.deal_id
            
            # Containers
            wizard.deal_containers = deal.total_containers if hasattr(deal, 'total_containers') else 0
            
            # Product mix
            if hasattr(deal, 'line_ids') and deal.line_ids:
                product_count = len(deal.line_ids.mapped('product_id'))
                wizard.product_mix = f"{product_count} product{'s' if product_count != 1 else ''}"
            else:
                wizard.product_mix = "No products"
    
    @api.depends('supplier_id', 'rts_date')
    def _compute_available_prs(self):
        """Find production runs that match this deal's supplier and date range"""
        for wizard in self:
            if not wizard.supplier_id:
                wizard.available_pr_ids = False
                wizard.available_pr_count = 0
                continue
            
            domain = [
                ('state', 'in', ['draft', 'confirmed']),
                ('supplier_id', '=', wizard.supplier_id.id)
            ]
            
            # Optional: Filter by RTS date proximity (±14 days)
            if wizard.rts_date:
                from datetime import timedelta
                date_from = wizard.rts_date - timedelta(days=14)
                date_to = wizard.rts_date + timedelta(days=14)
                domain.extend([
                    '|',
                    ('rts_date', '=', False),
                    '&',
                    ('rts_date', '>=', date_from),
                    ('rts_date', '<=', date_to)
                ])
            
            available_prs = self.env['dm.production.run'].search(domain, order='rts_date, id')
            wizard.available_pr_ids = available_prs
            wizard.available_pr_count = len(available_prs)
    
    @api.depends('production_run_id', 'deal_id', 'allocation_mode')
    def _compute_capacity_impact(self):
        """Calculate capacity impact of allocation"""
        for wizard in self:
            # Reset values
            wizard.show_capacity_warning = False
            wizard.capacity_warning_message = ''
            wizard.current_pr_teu = 0
            wizard.new_pr_teu = 0
            wizard.pr_capacity_teu = 0
            wizard.new_utilization = 0
            wizard.capacity_status_color = 'green'
            
            # Only calculate for existing PR
            if wizard.allocation_mode != 'existing' or not wizard.production_run_id or not wizard.deal_id:
                continue
            
            pr = wizard.production_run_id
            
            # Use PR's check method if available
            if hasattr(pr, 'check_can_allocate_deal'):
                result = pr.check_can_allocate_deal(wizard.deal_id)
                
                wizard.show_capacity_warning = bool(result.get('warning'))
                wizard.capacity_warning_message = result.get('warning', '')
                wizard.current_pr_teu = pr.total_teu if hasattr(pr, 'total_teu') else 0
                wizard.new_pr_teu = result.get('new_total_teu', 0)
                wizard.new_utilization = result.get('new_utilization', 0)
                
                # Get capacity
                if hasattr(pr, 'vendor_capacity_id') and pr.vendor_capacity_id:
                    wizard.pr_capacity_teu = pr.vendor_capacity_id.effective_capacity_teu
                elif hasattr(pr, 'month_capacity_teu'):
                    wizard.pr_capacity_teu = pr.month_capacity_teu
                
                # Determine color
                if wizard.new_utilization >= 100:
                    wizard.capacity_status_color = 'red'
                elif wizard.new_utilization >= 80:
                    wizard.capacity_status_color = 'yellow'
                else:
                    wizard.capacity_status_color = 'green'
            else:
                # Simple calculation without capacity check
                wizard.current_pr_teu = pr.total_teu if hasattr(pr, 'total_teu') else 0
                wizard.new_pr_teu = wizard.current_pr_teu + wizard.deal_teu
    
    # ========================================================================
    # ONCHANGE METHODS
    # ========================================================================
    
    @api.onchange('allocation_mode')
    def _onchange_allocation_mode(self):
        """Clear fields when switching mode"""
        if self.allocation_mode == 'existing':
            self.new_pr_rts_date = False
            self.new_pr_production_start = False
        else:  # new
            self.production_run_id = False
            # Pre-fill from deal
            if self.deal_id:
                self.new_pr_rts_date = self.deal_id.rts_current or self.deal_id.rts_requested
                if hasattr(self.deal_id, 'production_start_current'):
                    self.new_pr_production_start = self.deal_id.production_start_current
    
    @api.onchange('deal_id')
    def _onchange_deal_id(self):
        """Pre-fill new PR dates from deal"""
        if self.allocation_mode == 'new' and self.deal_id:
            self.new_pr_rts_date = self.deal_id.rts_current or self.deal_id.rts_requested
            if hasattr(self.deal_id, 'production_start_current'):
                self.new_pr_production_start = self.deal_id.production_start_current
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_allocate(self):
        """Perform the allocation"""
        self.ensure_one()
        
        # Validate
        if self.allocation_mode == 'existing':
            if not self.production_run_id:
                raise UserError(_('Please select a production run'))
            
            # Final capacity check
            if hasattr(self.production_run_id, 'check_can_allocate_deal'):
                result = self.production_run_id.check_can_allocate_deal(self.deal_id)
                if not result['can_allocate']:
                    raise ValidationError(_(
                        "Cannot allocate: %s\n\n"
                        "This would exceed capacity limits."
                    ) % result['warning'])
            
            pr = self.production_run_id
        
        else:  # new
            if not self.new_pr_rts_date:
                raise UserError(_('Please specify RTS date for new production run'))
            
            # Create new production run
            pr = self.env['dm.production.run'].create({
                'supplier_id': self.supplier_id.id,
                'rts_date': self.new_pr_rts_date,
                'production_start_date': self.new_pr_production_start,
            })
            _logger.info(f"Created new production run {pr.name} for deal {self.deal_id.name}")
        
        # Create allocation
        allocation = self.env['dm.allocation'].create({
            'deal_id': self.deal_id.id,
            'allocation_type': 'production',
            'production_run_id': pr.id,
            'state': 'active',
        })
        
        _logger.info(
            f"Quick allocated Deal {self.deal_id.name} to PR {pr.name}"
        )
        
        # Return success with option to view PR
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Allocated Successfully'),
                'message': _(
                    'Deal %s allocated to Production Run %s'
                ) % (self.deal_id.name, pr.name),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
    
    def action_view_production_run(self):
        """View the target production run"""
        self.ensure_one()
        if not self.production_run_id:
            return
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Run'),
            'res_model': 'dm.production.run',
            'res_id': self.production_run_id.id,
            'view_mode': 'form',
            'target': 'current',
        }