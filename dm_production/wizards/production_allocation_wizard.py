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
        """Allocate deals to production"""
        self.ensure_one()
        
        # Validate
        if self.create_new_pr:
            if not self.supplier_id:
                raise UserError(_('Supplier is required for new production run'))
        else:
            if not self.production_run_id:
                raise UserError(_('Please select a production run'))
        
        # Check deals are not already allocated to production
        already_allocated = self.deal_ids.filtered(lambda d: d.production_allocated)
        if already_allocated:
            raise UserError(_(
                'The following deals are already allocated to production: %s'
            ) % ', '.join(already_allocated.mapped('name')))
        
        # Create or get production run
        if self.create_new_pr:
            pr = self.env['dm.production.run'].create({
                'supplier_id': self.supplier_id.id,
                'production_start_date': self.production_start_date,
                'rts_date': self.rts_date,
            })
            _logger.info(f"Created production run {pr.name} for supplier {self.supplier_id.name}")
        else:
            pr = self.production_run_id
        
        # Create allocations
        allocations_created = 0
        for deal in self.deal_ids:
            allocation = self.env['dm.allocation'].create({
                'deal_id': deal.id,
                'allocation_type': 'production',
                'production_run_id': pr.id,
                'state': 'active',
            })
            allocations_created += 1
            
            # FIX #3: Update deal state ONLY if BOTH PR and Shipment allocated
            if deal.state == 'confirmed':
                # Check if shipment also allocated
                if deal.shipment_allocated:
                    deal.write({'state': 'allocated'})
                # If only production allocated, stay in 'confirmed'
            
            _logger.info(f"Allocated deal {deal.name} to production run {pr.name}")
        
        # FIX #5: Close wizard with success message
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