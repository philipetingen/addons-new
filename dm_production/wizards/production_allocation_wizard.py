# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ProductionAllocationWizard(models.TransientModel):
    """
    Production Allocation Wizard - BLACK BOX Implementation
    
    Simple wizard to allocate deals to production runs.
    """
    _name = 'dm.production.allocation.wizard'
    _description = 'Production Allocation Wizard'
    
    deal_ids = fields.Many2many(
        'dm.deal',
        string='Deals',
        required=True,
        help='Deals to allocate to production'
    )
    
    production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        domain=[('state', 'in', ['draft', 'confirmed'])],
        help='Existing production run to allocate to'
    )
    
    create_new_pr = fields.Boolean(
        string='Create New Production Run',
        default=True
    )
    
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('supplier_rank', '>', 0)],
        help='Supplier for new production run'
    )
    
    production_start_date = fields.Date(
        string='Production Start',
        help='Planned production start date'
    )
    
    rts_date = fields.Date(
        string='Target RTS Date',
        help='Target ready to ship date'
    )
    
    @api.onchange('create_new_pr')
    def _onchange_create_new_pr(self):
        """Clear production_run_id when creating new"""
        if self.create_new_pr:
            self.production_run_id = False
        else:
            self.supplier_id = False
            self.production_start_date = False
            self.rts_date = False
    
    @api.onchange('deal_ids')
    def _onchange_deal_ids(self):
        """Pre-fill fields from first deal"""
        if self.deal_ids and self.create_new_pr:
            deal = self.deal_ids[0]
            
            # Pre-fill supplier from deal
            if deal.supplier_id:
                self.supplier_id = deal.supplier_id
            
            # Pre-fill dates from deal
            if hasattr(deal, 'production_start_current') and deal.production_start_current:
                self.production_start_date = deal.production_start_current
            
            if deal.rts_current:
                self.rts_date = deal.rts_current
            elif deal.rts_requested:
                self.rts_date = deal.rts_requested
    
    def action_allocate(self):
        """Allocate deals to production with enhanced validation"""
        self.ensure_one()
        
        # Validate wizard inputs
        if self.create_new_pr:
            if not self.supplier_id:
                raise UserError(_('Supplier is required for new production run'))
        else:
            if not self.production_run_id:
                raise UserError(_('Please select a production run'))
        
        # ENHANCED VALIDATION: Check for ACTUAL active allocations with valid PRs
        Allocation = self.env['dm.allocation']
        ProductionRun = self.env['dm.production.run']
        
        for deal in self.deal_ids:
            # Search for active production allocations
            active_pr_allocs = Allocation.search([
                ('deal_id', '=', deal.id),
                ('allocation_type', '=', 'production'),
                ('state', '=', 'active'),
            ])
            
            # Filter to only those with valid, non-cancelled PRs
            valid_allocs = active_pr_allocs.filtered(
                lambda a: a.production_run_id 
                and a.production_run_id.exists() 
                and a.production_run_id.state != 'cancelled'
            )
            
            if valid_allocs:
                pr_names = ', '.join(valid_allocs.mapped('production_run_id.name'))
                raise UserError(_(
                    'Deal %s is already allocated to production run(s): %s. '
                    'Cannot create duplicate active allocation.'
                ) % (deal.name, pr_names))
        
        # Create or get production run
        if self.create_new_pr:
            pr_vals = {
                'supplier_id': self.supplier_id.id,
            }
            
            # Use new three-layer date fields if available
            if hasattr(ProductionRun, 'production_start_current'):
                if self.production_start_date:
                    pr_vals['production_start_current'] = self.production_start_date
                if self.rts_date:
                    pr_vals['rts_current'] = self.rts_date
            else:
                # Fallback to legacy fields
                if self.production_start_date:
                    pr_vals['production_start_date'] = self.production_start_date
                if self.rts_date:
                    pr_vals['rts_date'] = self.rts_date
            
            pr = ProductionRun.create(pr_vals)
            _logger.info(f"Created production run {pr.name} for supplier {self.supplier_id.name}")
        else:
            pr = self.production_run_id
        
        # Create allocations and production lines
        allocations_created = 0
        
        for deal in self.deal_ids:
            # Create allocation
            allocation = Allocation.create({
                'deal_id': deal.id,
                'allocation_type': 'production',
                'production_run_id': pr.id,
                'state': 'active',
            })
            allocations_created += 1
            
            # Auto-create production lines from deal lines
            if hasattr(self, '_create_production_lines_for_deal'):
                self._create_production_lines_for_deal(pr, deal)
            
            # Update deal state ONLY if BOTH PR and Shipment allocated
            if deal.state == 'confirmed':
                # Check if shipment also allocated
                shipment_allocated = any(
                    a.allocation_type == 'shipment' and a.state == 'active'
                    for a in deal.allocation_ids
                )
                
                if shipment_allocated:
                    deal.write({'state': 'allocated'})
                    _logger.info(f"Deal {deal.name} state → 'allocated' (both PR and Shipment)")
                else:
                    _logger.info(f"Deal {deal.name} remains 'confirmed' (only PR allocated)")
            
            _logger.info(f"✓ Allocated deal {deal.name} to production run {pr.name}")
        
        # Success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d deal(s) allocated to production run %s') % (
                    allocations_created, pr.name
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
        
    def _create_production_lines_for_deal(self, production_run, deal):
        """
        Auto-create production lines from deal lines
        Called after allocation is created
        """
        lines_created = []
        
        for deal_line in deal.line_ids:
            pr_line = self.env['dm.production.line'].create({
                'production_run_id': production_run.id,
                'deal_id': deal.id,
                'deal_line_id': deal_line.id,
                'product_id': deal_line.product_id.id,
                'product_packaging_id': deal_line.product_packaging_id.id,  # ✅ CORRECT
                'quantity_ordered': deal_line.quantity_packaging,  # ✅ CORRECT
                'quantity_produced': 0.0,
                'sequence': deal_line.sequence,
            })
            lines_created.append(pr_line)
        
        _logger.info(
            f"Created {len(lines_created)} production lines for deal {deal.name} "
            f"in PR {production_run.name}"
        )
        
        return lines_created