# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealProduction(models.Model):
    """
    Production planning extension for deals.
    
    Adds production scheduling, capacity awareness, and lot aggregation.
    Sprint 5A: Foundation layer for production tracking.
    
    NOTE: Uses milestone date fields from dm_deal.py core:
    - production_start_requested, production_start_current, production_start_actual
    - rts_requested, rts_current, rts_actual
    
    NO duplicate date fields - all production dates reference existing milestone fields.
    """
    _inherit = 'dm.deal'
    
    # =========================================================================
    # PRODUCTION STATUS
    # =========================================================================
    
    production_status = fields.Selection([
        ('not_planned', 'Not Planned'),
        ('planned', 'Planned'),
        ('in_production', 'In Production'),
        ('ready', 'Ready to Ship'),
        ('completed', 'Completed'),
    ], string='Production Status',
        default='not_planned',
        tracking=True,
        help='Production lifecycle status'
    )
    
    production_status_badge = fields.Selection([
        ('not_planned', 'Not Planned'),
        ('planned', 'Planned'),
        ('in_production', 'In Production'),
        ('ready', 'Ready to Ship'),
        ('completed', 'Completed'),
    ], string='Status',
        compute='_compute_production_status_badge',
        help='For badge widget display'
    )
    
    # =========================================================================
    # LOT TRACKING - AGGREGATED FROM LINES
    # =========================================================================
    
    lot_count = fields.Integer(
        compute='_compute_lot_count',
        string='# Lots',
        help='Total number of production lots across all deal lines'
    )
    
    has_lots = fields.Boolean(
        compute='_compute_lot_count',
        string='Has Lots',
        help='True if any lots recorded across deal lines'
    )
    
    total_lot_quantity = fields.Float(
        compute='_compute_lot_aggregates',
        string='Total Lot Qty',
        digits=(16, 3),
        help='Sum of all lot quantities across all lines'
    )
    
    # =========================================================================
    # CAPACITY INTEGRATION
    # =========================================================================
    
    vendor_capacity_id = fields.Many2one(
        'dm.vendor.capacity',
        string='Vendor Capacity',
        compute='_compute_vendor_capacity',
        store=True,
        help='Active capacity record for supplier'
    )
    
    capacity_check_status = fields.Selection([
        ('unknown', 'Not Checked'),
        ('ok', 'Within Capacity'),
        ('warning', 'Near Limit'),
        ('error', 'Over Capacity'),
        ('no_config', 'No Capacity Configured'),
    ], string='Capacity Status',
        default='unknown',
        help='Result of capacity validation'
    )
    
    capacity_check_message = fields.Html(
        string='Capacity Check Result',
        help='Detailed capacity check results'
    )
    
    capacity_last_checked = fields.Datetime(
        string='Last Capacity Check',
        readonly=True
    )
    
    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================
    
    @api.depends('production_status')
    def _compute_production_status_badge(self):
        """Mirror for badge widget"""
        for deal in self:
            deal.production_status_badge = deal.production_status
    
    @api.depends('line_ids', 'line_ids.lot_ids')
    def _compute_lot_count(self):
        """Count total lots across all lines"""
        for deal in self:
            deal.lot_count = sum(deal.line_ids.mapped('lot_count'))
            deal.has_lots = deal.lot_count > 0
    
    @api.depends('line_ids', 'line_ids.lot_ids', 'line_ids.lot_ids.quantity')
    def _compute_lot_aggregates(self):
        """Aggregate lot quantities from all lines"""
        for deal in self:
            total_qty = 0.0
            for line in deal.line_ids:
                if line.lot_ids:
                    total_qty += sum(line.lot_ids.mapped('quantity'))
            deal.total_lot_quantity = total_qty
    
    @api.depends('supplier_id', 'rts_current')
    def _compute_vendor_capacity(self):
        """Get active capacity record for supplier"""
        for deal in self:
            if not deal.supplier_id:
                deal.vendor_capacity_id = False
                continue
            
            # Use rts_current (milestone date)
            target_date = deal.rts_current
            if not target_date:
                deal.vendor_capacity_id = False
                continue
            
            # Find capacity active for target month
            month_start = target_date.replace(day=1)
            
            capacity = self.env['dm.vendor.capacity'].search([
                ('vendor_id', '=', deal.supplier_id.id),
                ('valid_from', '<=', month_start),
                '|', ('valid_to', '=', False), ('valid_to', '>=', month_start),
                ('active', '=', True)
            ], limit=1)
            
            deal.vendor_capacity_id = capacity
    
    # =========================================================================
    # PRODUCTION WORKFLOW ACTIONS
    # =========================================================================
    
    def action_plan_production(self):
        """
        Open production planning form.
        Sets status to 'planned' when dates entered.
        """
        self.ensure_one()
        
        if self.state not in ['confirmed', 'ready']:
            raise UserError(_('Deal must be confirmed before planning production'))
        
        # If already planned, just open form
        if self.production_status == 'not_planned':
            self.write({'production_status': 'planned'})
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Planning: %s') % self.name,
            'res_model': 'dm.deal',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_production_focus': True}
        }

    def write(self, vals):
        """Handle state rollbacks - reset production_status accordingly"""
        res = super().write(vals)
        
        # When state rolls back, adjust production_status
        if 'state' in vals:
            for deal in self:
                if deal.state == 'confirmed' and deal.production_status in ['in_production', 'ready', 'completed']:
                    # Rolled back to confirmed - reset to planned
                    deal.production_status = 'planned'
                    _logger.info(f"Deal {deal.name} rolled back to confirmed, reset production_status to planned")
                
                elif deal.state == 'draft' and deal.production_status != 'not_planned':
                    # Rolled back to draft - reset to not_planned
                    deal.production_status = 'not_planned'
                    _logger.info(f"Deal {deal.name} rolled back to draft, reset production_status to not_planned")
        
        return res
    
    def action_start_production(self):
        """
        Mark production as started.
        Sets actual start date, production status, AND deal state.
        Uses milestone field: production_start_actual
        """
        for deal in self:
            # Allow starting from 'planned' or 'not_planned' or if rolled back
            if deal.production_status not in ['planned', 'not_planned', 'ready', 'completed']:
                raise UserError(
                    _('Cannot start production from status: %s') % deal.production_status
                )
            
            deal.write({
                'production_start_actual': fields.Date.today(),
                'production_status': 'in_production',
                'state': 'in_production',
            })
            
            _logger.info(f"Production started for deal {deal.name}, state changed to 'in_production'")
    
    def action_mark_ready_to_ship(self):
        """
        Mark production as ready to ship.
        Should be called when all lots are produced.
        Uses milestone field: rts_actual
        """
        for deal in self:
            # Allow marking ready from in_production or if rolled back from ready
            if deal.production_status not in ['in_production', 'planned', 'ready']:
                raise UserError(
                    _('Cannot mark ready from status: %s') % deal.production_status
                )
            
            deal.write({
                'rts_actual': fields.Date.today(),
                'production_status': 'ready',
                'state': 'ready',
            })
            
            _logger.info(f"Deal {deal.name} marked ready to ship, state changed to 'ready'")
    
    def action_complete_production(self):
        """
        Mark production as completed.
        Typically called from shipment loading.
        """
        for deal in self:
            if deal.production_status != 'ready':
                raise UserError(
                    _('Can only complete deals that are ready. '
                      'Current status: %s') % deal.production_status
                )
            
            deal.write({
                'production_status': 'completed',
            })
            
            _logger.info(f"Production completed for deal {deal.name}")
    
    # =========================================================================
    # CAPACITY CHECKING
    # =========================================================================
    
    def action_check_capacity(self):
        """
        Run capacity check and display results.
        Warning only - never blocks.
        """
        self.ensure_one()
        
        if not self.supplier_id:
            self.write({
                'capacity_check_status': 'unknown',
                'capacity_check_message': '<p>No supplier selected</p>',
                'capacity_last_checked': fields.Datetime.now()
            })
            return self._show_capacity_result()
        
        target_date = self.rts_current
        if not target_date:
            self.write({
                'capacity_check_status': 'unknown',
                'capacity_check_message': '<p>No RTS date set</p>',
                'capacity_last_checked': fields.Datetime.now()
            })
            return self._show_capacity_result()
        
        # Check if capacity module available
        if 'dm.capacity.check.wizard' not in self.env:
            self.write({
                'capacity_check_status': 'no_config',
                'capacity_check_message': '<p>Capacity planning module not installed</p>',
                'capacity_last_checked': fields.Datetime.now()
            })
            return self._show_capacity_result()
        
        # Run check via capacity module wizard
        wizard = self.env['dm.capacity.check.wizard'].create({
            'vendor_id': self.supplier_id.id,
            'date_from': target_date.replace(day=1),
            'date_to': target_date,
        })
        
        wizard.action_check_capacity()
        
        # Store result
        if wizard.check_passed:
            status = 'ok'
        elif wizard.violation_count > 0:
            status = 'error'
        else:
            status = 'warning'
        
        self.write({
            'capacity_check_status': status,
            'capacity_check_message': wizard.result_message,
            'capacity_last_checked': fields.Datetime.now()
        })
        
        return self._show_capacity_result()
    
    def _show_capacity_result(self):
        """Return action to show capacity check results"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Capacity Check Complete'),
                'message': _('Status: %s') % dict(
                    self._fields['capacity_check_status'].selection
                ).get(self.capacity_check_status),
                'type': 'success' if self.capacity_check_status == 'ok' else 'warning',
                'sticky': False,
            }
        }
    
    # =========================================================================
    # VIEWS / ACTIONS
    # =========================================================================
    
    def action_view_lots(self):
        """View production lots for this deal"""
        self.ensure_one()
        
        return {
            'name': _('Production Lots: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal.line.lot',
            'view_mode': 'tree,form',
            'domain': [('deal_id', '=', self.id)],
            'context': {'default_deal_id': self.id},
        }
    
    def action_open_lot_wizard(self):
        """Open lot entry wizard for this deal"""
        self.ensure_one()
        
        return {
            'name': _('Enter Production Lots: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal.line.lot.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_deal_id': self.id,
            }
        }