# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class LoadingLotWizard(models.TransientModel):
    """Simplified Lot Management for Loading Context"""
    _name = 'loading.lot.wizard'
    _description = 'Loading Lot Management Wizard'
    
    # =========================================================================
    # CONTEXT
    # =========================================================================
    
    loading_wizard_line_id = fields.Many2one(
        'loading.confirmation.wizard.line',
        string='Loading Line',
        required=True,
        ondelete='cascade'
    )
    
    deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        required=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        related='deal_line_id.product_id',
        string='Product'
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        related='deal_line_id.product_packaging_id',
        string='Package Type'
    )
    
    # =========================================================================
    # LOTS ACCESS (RELATED, EDITABLE)
    # =========================================================================
    
    lot_ids = fields.One2many(
        'dm.deal.line.lot',
        related='deal_line_id.lot_ids',
        readonly=False,
        string='Lots'
    )
    
    # =========================================================================
    # QUANTITY LOADED (BILATERAL WITH WIZARD LINE)
    # =========================================================================
    
    quantity_loaded = fields.Float(
        string='Quantity Loaded',
        related='loading_wizard_line_id.quantity_loaded',
        readonly=False,
        digits=(16, 3),
        help='Quantity to allocate to lots (editable)'
    )
    
    # =========================================================================
    # ALLOCATION SUMMARY
    # =========================================================================
    
    total_allocated = fields.Float(
        string='Total Allocated',
        compute='_compute_allocation',
        digits=(16, 3)
    )
    
    remaining = fields.Float(
        string='Remaining',
        compute='_compute_allocation',
        digits=(16, 3)
    )
    
    @api.depends('lot_ids', 'lot_ids.quantity', 'quantity_loaded')
    def _compute_allocation(self):
        """Compute total and remaining from lots"""
        for wizard in self:
            total = sum(wizard.lot_ids.mapped('quantity'))
            wizard.total_allocated = total
            wizard.remaining = wizard.quantity_loaded - total
    
    # =========================================================================
    # VALIDATION (ONLY ON SAVE, NOT ONCHANGE)
    # =========================================================================
    
    @api.constrains('lot_ids', 'lot_ids.quantity', 'quantity_loaded')
    def _check_lot_allocation(self):
        """Prevent over-allocation (hard constraint)"""
        for wizard in self:
            if wizard.quantity_loaded <= 0:
                continue
            
            total_lots = sum(wizard.lot_ids.mapped('quantity'))
            if total_lots > wizard.quantity_loaded + 0.001:
                raise ValidationError(_(
                    'Total lot quantity (%.3f) exceeds loaded quantity (%.3f).\n'
                    'Reduce lot quantities or increase loaded quantity.'
                ) % (total_lots, wizard.quantity_loaded))
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def action_add_lot_auto(self):
        """Add new lot with remaining quantity auto-filled"""
        self.ensure_one()
        
        remaining = self.quantity_loaded - sum(self.lot_ids.mapped('quantity'))
        
        if remaining <= 0.001:
            raise UserError(_('All quantity already allocated. Adjust existing lots or increase loaded quantity.'))
        
        # Create new lot
        new_lot = self.env['dm.deal.line.lot'].create({
            'deal_line_id': self.deal_line_id.id,
            'lot_number': f'LOT-{len(self.lot_ids) + 1}',
            'quantity': remaining,
            'production_date': fields.Date.today(),
            'expiry_date': fields.Date.today(),  # User will adjust
        })
        
        # Reload wizard to show new lot
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'loading.lot.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_save(self):
        """Save - validate and inform user of issues"""
        self.ensure_one()
        
        if self.quantity_loaded <= 0:
            raise UserError(_('Quantity loaded must be greater than zero'))
        
        total_lots = sum(self.lot_ids.mapped('quantity'))
        diff = abs(total_lots - self.quantity_loaded)
        
        # Check allocation
        if diff > 0.001:
            if total_lots < self.quantity_loaded:
                # Under-allocated - inform user
                raise UserError(_(
                    'Lot allocation incomplete.\n\n'
                    'Quantity Loaded: %.3f\n'
                    'Total Allocated: %.3f\n'
                    'Remaining: %.3f\n\n'
                    'You must allocate all loaded quantity to lots before saving.\n'
                    'Click "Add Lot" to create a lot with the remaining quantity.'
                ) % (self.quantity_loaded, total_lots, self.quantity_loaded - total_lots))
            else:
                # Over-allocated - should be caught by constraint, but just in case
                raise UserError(_(
                    'Total lot quantity (%.3f) exceeds loaded quantity (%.3f).\n'
                    'Reduce lot quantities before saving.'
                ) % (total_lots, self.quantity_loaded))
        
        # All good - close and return to loading wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'loading.confirmation.wizard',
            'res_id': self.loading_wizard_line_id.wizard_id.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_discard(self):
        """Discard - return to loading wizard without validation"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'loading.confirmation.wizard',
            'res_id': self.loading_wizard_line_id.wizard_id.id,
            'view_mode': 'form',
            'target': 'new',
        }