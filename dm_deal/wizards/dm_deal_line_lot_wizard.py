# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDealLineLotWizard(models.TransientModel):
    """Lot Management Wizard for Deal Lines
    
    Allows splitting a deal line into multiple lots with different
    production dates and lot numbers.
    """
    _name = 'dm.deal.line.lot.wizard'
    _description = 'Deal Line Lot Management Wizard'
    
    # ========================================================================
    # HEADER FIELDS
    # ========================================================================
    
    deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        required=True,
        readonly=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        related='deal_line_id.product_id',
        readonly=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Package Type',
        related='deal_line_id.product_packaging_id',
        readonly=True
    )
    
    quantity_target = fields.Float(
        string='Target Quantity (Pkg)',
        readonly=True,
        digits=(16, 3),
        help="Target quantity to allocate across lots (from quantity_loaded)"
    )
    
    # ========================================================================
    # LOT LINES
    # ========================================================================
    
    lot_line_ids = fields.One2many(
        'dm.deal.line.lot.wizard.line',
        'wizard_id',
        string='Lot Lines'
    )
    
    # ========================================================================
    # SUMMARY FIELDS
    # ========================================================================
    
    total_quantity = fields.Float(
        string='Total Allocated (Pkg)',
        compute='_compute_totals',
        digits=(16, 3)
    )
    
    remaining_quantity = fields.Float(
        string='Remaining (Pkg)',
        compute='_compute_totals',
        digits=(16, 3)
    )
    
    quantity_matches = fields.Boolean(
        string='Quantities Match',
        compute='_compute_totals',
        help="True when total allocated equals target"
    )
    
    allocation_status = fields.Selection([
        ('under', 'Under-allocated'),
        ('exact', 'Exact Match'),
        ('over', 'Over-allocated')
    ], compute='_compute_totals',
        string='Allocation Status'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('lot_line_ids.quantity', 'quantity_target')
    def _compute_totals(self):
        """Calculate totals and allocation status"""
        for wizard in self:
            total = sum(wizard.lot_line_ids.mapped('quantity'))
            wizard.total_quantity = total
            wizard.remaining_quantity = wizard.quantity_target - total
            wizard.quantity_matches = abs(wizard.remaining_quantity) < 0.001
            
            # Allocation status
            if wizard.remaining_quantity < -0.001:
                wizard.allocation_status = 'over'
            elif wizard.remaining_quantity > 0.001:
                wizard.allocation_status = 'under'
            else:
                wizard.allocation_status = 'exact'
    
    # ========================================================================
    # DEFAULT VALUES
    # ========================================================================
    
    @api.model
    def default_get(self, fields_list):
        """Pre-populate wizard with existing lots or create default single lot"""
        res = super().default_get(fields_list)
        
        # Get deal line from context
        deal_line_id = self.env.context.get('default_deal_line_id')
        if not deal_line_id:
            return res
        
        line = self.env['dm.deal.line'].browse(deal_line_id)
        
        res['deal_line_id'] = deal_line_id
        res['quantity_target'] = self.env.context.get('default_quantity_target', line.quantity_loaded or line.quantity_packaging)
        
        # Load existing lots or create default
        if line.lot_ids:
            # Edit mode: Load existing lots
            res['lot_line_ids'] = [(0, 0, {
                'lot_id': lot.id,
                'lot_number': lot.lot_number,
                'quantity': lot.quantity,
                'production_date': lot.production_date,
                'expiry_date': lot.expiry_date,
                'notes': lot.notes,
            }) for lot in line.lot_ids.sorted('sequence')]
        else:
            # Create mode: Single lot with full quantity
            default_expiry = False
            product_tmpl = line.product_id.product_tmpl_id
            if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                default_expiry = fields.Date.today() + timedelta(days=product_tmpl.production_to_expiry_days)
            
            res['lot_line_ids'] = [(0, 0, {
                'lot_number': line.single_lot_number or '',
                'quantity': res['quantity_target'],
                'production_date': line.single_lot_production_date or fields.Date.today(),
                'expiry_date': line.single_lot_expiry_date or default_expiry,
                'sequence': 10,
            })]
        
        return res
    
    # ========================================================================
    # ACTIONS
    # ========================================================================
    
    def action_add_lot(self):
        """Add a new lot line with remaining quantity"""
        self.ensure_one()
        
        # Force recompute totals
        self._compute_totals()
        
        if self.remaining_quantity <= 0:
            raise UserError(_('No remaining quantity to allocate to a new lot.\nCurrent allocation: %.2f / %.2f') % 
                          (self.total_quantity, self.quantity_target))
        
        # Calculate default expiry
        default_expiry = False
        product_tmpl = self.product_id.product_tmpl_id
        if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
            default_expiry = fields.Date.today() + timedelta(days=product_tmpl.production_to_expiry_days)
        
        # Get next sequence
        max_seq = max(self.lot_line_ids.mapped('sequence') or [0])
        
        # Create new lot line
        new_vals = {
            'wizard_id': self.id,
            'lot_number': '',
            'quantity': self.remaining_quantity,
            'production_date': fields.Date.today(),
            'expiry_date': default_expiry,
            'sequence': max_seq + 10,
        }
        
        _logger.info('Adding new lot line with remaining qty: %.2f', self.remaining_quantity)
        
        new_line = self.env['dm.deal.line.lot.wizard.line'].create(new_vals)
        
        _logger.info('Created wizard line ID: %s', new_line.id)
        
        # Refresh wizard view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal.line.lot.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_save_lots(self):
        """Save lot details to deal line"""
        self.ensure_one()
        
        _logger.info('=== LOT WIZARD SAVE START ===')
        _logger.info('Wizard ID: %s', self.id)
        _logger.info('Deal line: %s (ID: %s)', self.deal_line_id.product_id.name, self.deal_line_id.id)
        _logger.info('Target quantity: %.2f', self.quantity_target)
        _logger.info('Wizard lot lines count: %d', len(self.lot_line_ids))
        
        # Validate total matches target
        if not self.quantity_matches:
            raise ValidationError(_(
                'Total lot quantity (%.2f) must equal target quantity (%.2f)\n'
                'Remaining: %.2f packages\n\n'
                'Please adjust lot quantities or add/remove lots.'
            ) % (self.total_quantity, self.quantity_target, self.remaining_quantity))
        
        # Validate all lots have required data
        for lot_line in self.lot_line_ids:
            if not lot_line.lot_number:
                raise ValidationError(_('All lots must have a lot/batch number'))
            if not lot_line.production_date:
                raise ValidationError(_('All lots must have a production date'))
            if lot_line.quantity <= 0:
                raise ValidationError(_('All lots must have positive quantity'))
            
            # Validate expiry after production
            if lot_line.production_date and lot_line.expiry_date:
                if lot_line.expiry_date < lot_line.production_date:
                    raise ValidationError(_(
                        'Expiry date (%s) cannot be earlier than production date (%s) for lot %s'
                    ) % (lot_line.expiry_date, lot_line.production_date, lot_line.lot_number or 'new'))
        
        # Track which lots to keep
        lots_to_keep = []
        
        # Process each wizard line
        for lot_line in self.lot_line_ids:
            lot_vals = {
                'lot_number': lot_line.lot_number,
                'quantity': lot_line.quantity,
                'production_date': lot_line.production_date,
                'expiry_date': lot_line.expiry_date,
                'notes': lot_line.notes,
                'sequence': lot_line.sequence,
            }
            
            if lot_line.lot_id:
                # Update existing lot
                _logger.info('Updating existing lot %s: %s', lot_line.lot_id.id, lot_vals)
                lot_line.lot_id.write(lot_vals)
                lots_to_keep.append(lot_line.lot_id.id)
            else:
                # Create new lot
                lot_vals['deal_line_id'] = self.deal_line_id.id
                _logger.info('Creating new lot: %s', lot_vals)
                new_lot = self.env['dm.deal.line.lot'].create(lot_vals)
                _logger.info('Created lot ID: %s', new_lot.id)
                lots_to_keep.append(new_lot.id)
        
        # Get all existing lots for this line
        all_existing_lot_ids = self.deal_line_id.lot_ids.ids
        _logger.info('All lots in DB before cleanup: %s', all_existing_lot_ids)
        _logger.info('Lots to keep: %s', lots_to_keep)
        
        # Delete lots that are no longer in wizard
        lots_to_delete_ids = [lid for lid in all_existing_lot_ids if lid not in lots_to_keep]
        
        if lots_to_delete_ids:
            _logger.info('Deleting lots: %s', lots_to_delete_ids)
            lots_to_delete = self.env['dm.deal.line.lot'].browse(lots_to_delete_ids)
            lots_to_delete.unlink()
        
        # Update deal line quantity_loaded to match total
        self.deal_line_id.write({
            'quantity_loaded': self.total_quantity
        })
        
        # Force refresh of deal line computed fields
        self.deal_line_id.invalidate_recordset(['lot_ids', 'lot_count', 'total_lotted_quantity', 'has_multiple_lots'])
        
        # Explicitly recompute
        self.deal_line_id._compute_lot_info()
        
        _logger.info('Final lot IDs in deal line: %s', self.deal_line_id.lot_ids.ids)
        _logger.info('Final lot count: %d', self.deal_line_id.lot_count)
        _logger.info('=== LOT WIZARD SAVE END ===')
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_cancel(self):
        """Cancel wizard without saving"""
        return {'type': 'ir.actions.act_window_close'}


class DmDealLineLotWizardLine(models.TransientModel):
    """Lot Wizard Line - Transient record for lot data entry"""
    _name = 'dm.deal.line.lot.wizard.line'
    _description = 'Deal Line Lot Wizard Line'
    _order = 'sequence, id'
    
    # ========================================================================
    # HEADER
    # ========================================================================
    
    wizard_id = fields.Many2one(
        'dm.deal.line.lot.wizard',
        required=True,
        ondelete='cascade'
    )
    
    sequence = fields.Integer(
        default=10,
        string='Sequence'
    )
    
    lot_id = fields.Many2one(
        'dm.deal.line.lot',
        string='Existing Lot',
        help='Reference to existing lot if editing'
    )
    
    # ========================================================================
    # LOT DATA
    # ========================================================================
    
    lot_number = fields.Char(
        string='Lot/Batch Number',
        required=True,
        help="Factory lot or batch number"
    )
    
    quantity = fields.Float(
        string='Quantity (Pkg)',
        digits=(16, 3),
        required=True,
        help="Quantity in packages for this lot"
    )
    
    production_date = fields.Date(
        string='Production Date',
        required=True,
        default=fields.Date.today,
        help="Date this lot was produced"
    )
    
    expiry_date = fields.Date(
        string='Expiry Date',
        help="Expiry date for this lot"
    )
    
    notes = fields.Text(
        string='Notes',
        help="Additional notes about this lot"
    )
    
    # ========================================================================
    # DISPLAY HELPERS
    # ========================================================================
    
    product_id = fields.Many2one(
        'product.product',
        related='wizard_id.product_id',
        string='Product',
        readonly=True
    )
    
    # ========================================================================
    # ONCHANGE METHODS
    # ========================================================================
    
    @api.onchange('quantity')
    def _onchange_quantity(self):
        """When quantity changes, trigger wizard totals recompute"""
        if self.wizard_id:
            self.wizard_id._compute_totals()
    
    @api.onchange('production_date')
    def _onchange_production_date(self):
        """Auto-calculate expiry date from production date + product shelf life"""
        if self.production_date and self.wizard_id.product_id:
            product_tmpl = self.wizard_id.product_id.product_tmpl_id
            if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                self.expiry_date = self.production_date + timedelta(days=product_tmpl.production_to_expiry_days)
    
    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    @api.constrains('quantity')
    def _check_quantity_positive(self):
        """Quantity must be positive"""
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_(
                    'Lot quantity must be positive. Got: %.3f'
                ) % line.quantity)
    
    @api.constrains('production_date', 'expiry_date')
    def _check_expiry_after_production(self):
        """Expiry date must be after production date"""
        for line in self:
            if line.production_date and line.expiry_date:
                if line.expiry_date < line.production_date:
                    raise ValidationError(_(
                        'Expiry date (%s) cannot be earlier than production date (%s)'
                    ) % (line.expiry_date, line.production_date))