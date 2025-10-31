# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class ProductionLotWizard(models.TransientModel):
    _name = 'production.lot.wizard'
    _description = 'Production Lot Creation Wizard'
    
    production_line_id = fields.Many2one(
        'dm.production.line',
        string='Production Line',
        required=True,
        readonly=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        readonly=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Package Type',
        readonly=True
    )
    
    quantity_produced = fields.Float(
        string='Produced Quantity (Pkg)',
        readonly=True,
        digits=(16, 3)
    )
    
    lot_line_ids = fields.One2many(
        'production.lot.wizard.line',
        'wizard_id',
        string='Lot Lines'
    )
    
    total_quantity = fields.Float(
        string='Total Lotted (Pkg)',
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
        compute='_compute_totals'
    )
    
    @api.depends('lot_line_ids.quantity', 'quantity_produced')
    def _compute_totals(self):
        """Calculate totals and check if complete"""
        for wizard in self:
            total = sum(wizard.lot_line_ids.mapped('quantity'))
            wizard.total_quantity = total
            wizard.remaining_quantity = wizard.quantity_produced - total
            wizard.quantity_matches = abs(wizard.remaining_quantity) < 0.001
    
    @api.model
    def default_get(self, fields_list):
        """Pre-populate wizard with existing lots or create default single lot"""
        res = super().default_get(fields_list)
        
        if 'production_line_id' in self.env.context:
            line_id = self.env.context['production_line_id']
            line = self.env['dm.production.line'].browse(line_id)
            
            res['production_line_id'] = line_id
            
            # Set product and packaging directly (not related)
            res['product_id'] = line.product_id.id
            res['product_packaging_id'] = line.product_packaging_id.id
            res['quantity_produced'] = line.quantity_produced
            
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
                }) for lot in line.lot_ids]
            else:
                # Create mode: Single lot with full quantity
                default_expiry = False
                product_tmpl = line.product_id.product_tmpl_id
                if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                    default_expiry = fields.Date.today() + timedelta(days=product_tmpl.production_to_expiry_days)
                
                res['lot_line_ids'] = [(0, 0, {
                    'quantity': line.quantity_produced,
                    'production_date': fields.Date.today(),
                    'expiry_date': default_expiry,
                })]
        
        return res
    
    def action_add_lot(self):
        """Add a new lot line with remaining quantity"""
        self.ensure_one()
        
        # Force recompute totals
        self._compute_totals()
        
        if self.remaining_quantity <= 0:
            raise UserError(_('No remaining quantity to allocate to a new lot'))
        
        # Calculate default expiry
        default_expiry = False
        product_tmpl = self.product_id.product_tmpl_id
        if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
            default_expiry = fields.Date.today() + timedelta(days=product_tmpl.production_to_expiry_days)
        
        # Get next sequence
        max_seq = max(self.lot_line_ids.mapped('sequence') or [0])
        
        # Create new lot line directly in the One2many
        new_vals = {
            'wizard_id': self.id,
            'quantity': self.remaining_quantity,
            'production_date': fields.Date.today(),
            'expiry_date': default_expiry,
            'sequence': max_seq + 10,
        }
        
        _logger.info('Adding new lot line with remaining qty: %.2f', self.remaining_quantity)
        
        # Create the wizard line record
        new_line = self.env['production.lot.wizard.line'].create(new_vals)
        
        _logger.info('Created wizard line ID: %s', new_line.id)
        
        # Refresh wizard view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'production.lot.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_save_lots(self):
        """Save lot details to production line"""
        self.ensure_one()
        
        _logger.info('=== WIZARD SAVE START ===')
        _logger.info('Wizard ID: %s', self.id)
        _logger.info('Wizard lot lines count: %d', len(self.lot_line_ids))
        _logger.info('Production line: %s (ID: %s)', self.production_line_id.name_get()[0][1], self.production_line_id.id)
        
        # Log each wizard line
        for idx, lot_line in enumerate(self.lot_line_ids):
            _logger.info('Wizard line %d: %s (qty: %.2f, wizard_line_id: %s, lot_id: %s)',
                        idx + 1, lot_line.lot_number, lot_line.quantity, lot_line.id, lot_line.lot_id.id if lot_line.lot_id else 'NEW')
        
        # Validate total matches produced
        if not self.quantity_matches:
            raise ValidationError(_(
                'Total lot quantity (%.2f) must equal produced quantity (%.2f)\n'
                'Remaining: %.2f packages'
            ) % (self.total_quantity, self.quantity_produced, self.remaining_quantity))
        
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
            }
            
            if lot_line.lot_id:
                # Update existing lot
                _logger.info('Updating existing lot %s: %s', lot_line.lot_id.id, lot_vals)
                lot_line.lot_id.write(lot_vals)
                lots_to_keep.append(lot_line.lot_id.id)
            else:
                # Create new lot
                lot_vals['production_line_id'] = self.production_line_id.id
                _logger.info('Creating new lot: %s', lot_vals)
                new_lot = self.env['dm.production.lot'].create(lot_vals)
                _logger.info('Created lot ID: %s', new_lot.id)
                lots_to_keep.append(new_lot.id)
        
        # Get all existing lots for this line
        all_existing_lot_ids = self.production_line_id.lot_ids.ids
        _logger.info('All lots in DB before cleanup: %s', all_existing_lot_ids)
        _logger.info('Lots to keep: %s', lots_to_keep)
        
        # Delete lots that are no longer in wizard
        lots_to_delete_ids = [lid for lid in all_existing_lot_ids if lid not in lots_to_keep]
        
        if lots_to_delete_ids:
            _logger.info('Deleting lots: %s', lots_to_delete_ids)
            lots_to_delete = self.env['dm.production.lot'].browse(lots_to_delete_ids)
            lots_to_delete.unlink()
        
        # Force refresh of production line computed fields
        self.production_line_id.invalidate_recordset(['lot_ids', 'lot_count', 'total_lotted_quantity', 'unlotted_quantity', 'lots_complete'])
        
        # Explicitly recompute
        self.production_line_id._compute_lot_count()
        self.production_line_id._compute_lot_totals()
        
        _logger.info('Final lot IDs in production line: %s', self.production_line_id.lot_ids.ids)
        _logger.info('Final lot count: %d', self.production_line_id.lot_count)
        _logger.info('=== WIZARD SAVE END ===')
        
        return {'type': 'ir.actions.act_window_close'}


class ProductionLotWizardLine(models.TransientModel):
    _name = 'production.lot.wizard.line'
    _description = 'Production Lot Wizard Line'
    _order = 'sequence, id'
    
    wizard_id = fields.Many2one(
        'production.lot.wizard',
        required=True,
        ondelete='cascade'
    )
    
    sequence = fields.Integer(default=10)
    
    lot_id = fields.Many2one(
        'dm.production.lot',
        string='Existing Lot',
        help='Reference to existing lot if editing'
    )
    
    lot_number = fields.Char(
        string='Lot/Batch Number',
        required=True
    )
    
    quantity = fields.Float(
        string='Quantity (Pkg)',
        digits=(16, 3),
        required=True
    )
    
    production_date = fields.Date(
        string='Production Date',
        required=True,
        default=fields.Date.today
    )
    
    expiry_date = fields.Date(
        string='Expiry Date'
    )
    
    notes = fields.Text(string='Notes')
    
    @api.onchange('quantity')
    def _onchange_quantity(self):
        """When quantity changes, trigger wizard totals recompute"""
        if self.wizard_id:
            # Trigger recompute
            self.wizard_id._compute_totals()
    
    @api.onchange('production_date')
    def _onchange_production_date(self):
        """Auto-calculate expiry date"""
        if self.production_date and self.wizard_id.product_id:
            product_tmpl = self.wizard_id.product_id.product_tmpl_id
            if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                self.expiry_date = self.production_date + timedelta(days=product_tmpl.production_to_expiry_days)