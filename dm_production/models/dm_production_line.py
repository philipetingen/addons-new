# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmProductionLine(models.Model):
    _name = 'dm.production.line'
    _description = 'Production Run Line'
    _order = 'production_run_id, sequence, id'
    
    # ========================================================================
    # HEADER
    # ========================================================================
    
    production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    state = fields.Selection(
        related='production_run_id.state',
        string='PR State',
        store=True,
        readonly=True
    )
    
    # ========================================================================
    # LOT DETAILS
    # ========================================================================
    
    lot_ids = fields.One2many(
        'dm.production.lot',
        'production_line_id',
        string='Lot Details',
        help='Factory lot/batch details for traceability'
    )
    
    lot_count = fields.Integer(
        string='Lot Count',
        compute='_compute_lot_count',
        store=True
    )
    
    total_lotted_quantity = fields.Float(
        string='Total Lotted (Pkg)',
        compute='_compute_lot_totals',
        store=True,
        digits=(16, 3),
        help='Sum of all lot quantities'
    )
    
    unlotted_quantity = fields.Float(
        string='Unlotted (Pkg)',
        compute='_compute_lot_totals',
        store=True,
        digits=(16, 3),
        help='Produced quantity not yet assigned to lots'
    )
    
    lots_complete = fields.Boolean(
        string='Lots Complete',
        compute='_compute_lot_totals',
        store=True,
        help='True when all produced quantity is lotted'
    )
    
    # ========================================================================
    # SOURCE
    # ========================================================================
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        ondelete='restrict',
        index=True
    )
    
    deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        required=True,
        ondelete='restrict',
        index=True,
        help='Source deal line for this production line'
    )
    
    # ========================================================================
    # PRODUCT & PACKAGING
    # ========================================================================
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        readonly=True,
        help='Denormalized from deal line'
    )
    
    product_name = fields.Char(
        related='product_id.name',
        string='Product Name',
        readonly=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Package Type',
        required=True,
        readonly=True,
        help='Denormalized from deal line'
    )
    
    packaging_name = fields.Char(
        related='product_packaging_id.name',
        string='Package',
        readonly=True
    )
    
    packaging_qty = fields.Float(
        related='product_packaging_id.qty',
        string='Units/Package',
        readonly=True
    )
    
    # ========================================================================
    # QUANTITIES (PACKAGE-NATIVE)
    # ========================================================================
    
    quantity_ordered = fields.Float(
        string='Ordered (Pkg)',
        digits=(16, 3),
        required=True,
        readonly=True,
        help='Ordered quantity from deal line (packages)'
    )
    
    quantity_produced = fields.Float(
        string='Produced (Pkg)',
        digits=(16, 3),
        default=0.0,
        help='Actually produced quantity (packages)'
    )
    
    quantity_loaded = fields.Float(
        string='Loaded (Pkg)',
        digits=(16, 3),
        readonly=True,
        help='Actual quantity loaded onto shipment (synced from Shipment in Step 5)'
    )

    quantity_loaded_units = fields.Float(
        string='Loaded (Units)',
        compute='_compute_unit_quantities',
        store=True,
        digits=(16, 3),
        help='Loaded quantity in units (reference only)'
    )

    quantity_produced_readonly = fields.Boolean(
        string='Quantity Produced Readonly',
        compute='_compute_quantity_readonly',
        help='Lock quantity_produced at ready_to_ship and beyond'
    )
    
    quantity_variance = fields.Float(
        string='Variance (Pkg)',
        compute='_compute_variance',
        store=True,
        digits=(16, 3),
        help='Produced - Ordered (negative = shortage)'
    )
    
    variance_percent = fields.Float(
        string='Variance %',
        compute='_compute_variance',
        store=True,
        digits=(16, 2),
        help='Variance as percentage of ordered'
    )
    
    # Unit quantities (reference only)
    quantity_ordered_units = fields.Float(
        string='Ordered (Units)',
        compute='_compute_unit_quantities',
        store=True,
        digits=(16, 3),
        help='Ordered quantity in units (reference only)'
    )
    
    quantity_produced_units = fields.Float(
        string='Produced (Units)',
        compute='_compute_unit_quantities',
        store=True,
        digits=(16, 3),
        help='Produced quantity in units (reference only)'
    )
    
    # ========================================================================
    # CONTAINER & TEU (COMPUTED FROM DEAL LINE PATTERN)
    # ========================================================================
    
    container_type_id = fields.Many2one(
        'dm.container.type',
        string='Container Type',
        compute='_compute_container_info',
        store=True,
        help='Container type from product'
    )
    
    containers_ordered = fields.Float(
        string='Containers Ordered',
        compute='_compute_container_info',
        store=True,
        digits=(16, 3),
        help='Containers for ordered quantity'
    )
    
    containers_produced = fields.Float(
        string='Containers Produced',
        compute='_compute_container_info',
        store=True,
        digits=(16, 3),
        help='Containers for produced quantity'
    )
    
    teu_ordered = fields.Float(
        string='TEU Ordered',
        compute='_compute_container_info',
        store=True,
        digits=(16, 2),
        help='TEU for ordered quantity'
    )
    
    teu_produced = fields.Float(
        string='TEU Produced',
        compute='_compute_container_info',
        store=True,
        digits=(16, 2),
        help='TEU for produced quantity'
    )
    
    # ========================================================================
    # NOTES
    # ========================================================================
    
    notes = fields.Text(
        string='Production Notes',
        help='Notes about production of this line'
    )
    
    # ========================================================================
    # INLINE LOT MANAGEMENT (1:1 SCENARIO)
    # ========================================================================
    
    # Display fields for inline editing (single lot scenario)
    lot_number_inline = fields.Char(
        string='Lot Number',
        compute='_compute_inline_lot_fields',
        inverse='_inverse_inline_lot_fields',
        store=False,
        help='Lot number for single-lot scenario (inline editing)'
    )
    
    production_date_inline = fields.Date(
        string='Production Date',
        compute='_compute_inline_lot_fields',
        inverse='_inverse_inline_lot_fields',
        store=False,
        default=fields.Date.today,
        help='Production date for single-lot scenario (inline editing)'
    )
    
    expiry_date_inline = fields.Date(
        string='Expiry Date',
        compute='_compute_inline_lot_fields',
        inverse='_inverse_inline_lot_fields',
        store=False,
        help='Expiry date for single-lot scenario (inline editing)'
    )
    
    lot_notes_inline = fields.Text(
        string='Lot Notes',
        compute='_compute_inline_lot_fields',
        inverse='_inverse_inline_lot_fields',
        store=False,
        help='Notes for single-lot scenario (inline editing)'
    )
    
    can_edit_inline = fields.Boolean(
        string='Can Edit Inline',
        compute='_compute_can_edit_inline',
        help='True if line has 0 or 1 lot (can use inline editing)'
    )
    
    lot_display = fields.Char(
        string='Lots',
        compute='_compute_lot_display',
        help='Display lot information in tree'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('quantity_ordered', 'quantity_produced')
    def _compute_variance(self):
        """Calculate quantity variance"""
        for line in self:
            line.quantity_variance = line.quantity_produced - line.quantity_ordered
            
            if line.quantity_ordered:
                line.variance_percent = (line.quantity_variance / line.quantity_ordered) * 100
            else:
                line.variance_percent = 0.0

    @api.depends(
        'quantity_ordered', 
        'quantity_produced',
        'quantity_loaded',  # NEW
        'packaging_qty'
    )
    def _compute_unit_quantities(self):
        """Convert package quantities to units"""
        for line in self:
            line.quantity_ordered_units = line.quantity_ordered * line.packaging_qty
            line.quantity_produced_units = line.quantity_produced * line.packaging_qty
            line.quantity_loaded_units = line.quantity_loaded * line.packaging_qty  # NEW

    @api.depends('production_run_id.state')
    def _compute_quantity_readonly(self):
        """
        Lock quantity_produced at ready_to_ship state.
        
        Editable states: draft, confirmed, in_production, qc_pending
        Locked states: ready, completed, cancelled
        """
        for line in self:
            lock_states = ['ready', 'completed', 'cancelled']
            line.quantity_produced_readonly = (
                line.production_run_id.state in lock_states
            )
    
    @api.depends('lot_ids')
    def _compute_lot_count(self):
        """Count lots for this line"""
        for line in self:
            line.lot_count = len(line.lot_ids)
    
    @api.depends('lot_ids.quantity', 'quantity_produced')
    def _compute_lot_totals(self):
        """Calculate total lotted quantity and check completion"""
        for line in self:
            total = sum(line.lot_ids.mapped('quantity'))
            line.total_lotted_quantity = total
            line.unlotted_quantity = line.quantity_produced - total
            line.lots_complete = (
                line.quantity_produced > 0 and 
                abs(total - line.quantity_produced) < 0.001
            )
            
            # Debug logging
            if line.lot_ids:
                _logger.info(
                    'Line %s: %d lots, total lotted: %.2f, produced: %.2f, complete: %s',
                    line.product_name, len(line.lot_ids), total, 
                    line.quantity_produced, line.lots_complete
                )
    
    @api.depends('lot_ids')
    def _compute_can_edit_inline(self):
        """Determine if inline editing is allowed (0 or 1 lot only)"""
        for line in self:
            line.can_edit_inline = len(line.lot_ids) <= 1
    
    @api.depends('lot_ids', 'lot_count')
    def _compute_lot_display(self):
        """Display lot info in tree view"""
        for line in self:
            if line.lot_count == 0:
                line.lot_display = ''
            elif line.lot_count == 1:
                lot = line.lot_ids[0]
                line.lot_display = lot.lot_number
            else:
                line.lot_display = f"Multiple ({line.lot_count})"
    
    @api.depends('lot_ids.lot_number', 'lot_ids.production_date', 
                 'lot_ids.expiry_date', 'lot_ids.notes')
    def _compute_inline_lot_fields(self):
        """Load lot fields for inline editing (single lot only)"""
        for line in self:
            if len(line.lot_ids) == 1:
                lot = line.lot_ids[0]
                line.lot_number_inline = lot.lot_number
                line.production_date_inline = lot.production_date
                line.expiry_date_inline = lot.expiry_date
                line.lot_notes_inline = lot.notes
            elif len(line.lot_ids) == 0:
                # New lot - set defaults
                line.lot_number_inline = False
                line.production_date_inline = fields.Date.today()
                line.expiry_date_inline = False
                line.lot_notes_inline = False
            else:
                line.lot_number_inline = False
                line.production_date_inline = False
                line.expiry_date_inline = False
                line.lot_notes_inline = False
    
    @api.onchange('production_date_inline')
    def _onchange_production_date_inline(self):
        """Auto-calculate expiry date when production date changes (inline mode)"""
        for line in self:
            if line.production_date_inline and line.product_id:
                product_tmpl = line.product_id.product_tmpl_id
                if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                    line.expiry_date_inline = line.production_date_inline + timedelta(days=product_tmpl.production_to_expiry_days)
    
    def _inverse_inline_lot_fields(self):
        """Save inline lot fields (create or update single lot)"""
        for line in self:
            # Only allow if 0 or 1 lot
            if len(line.lot_ids) > 1:
                continue
            
            # Skip if no data provided
            if not line.lot_number_inline and not line.production_date_inline:
                continue
            
            # Calculate default expiry if not provided
            expiry_date = line.expiry_date_inline
            if line.production_date_inline and not expiry_date:
                product_tmpl = line.product_id.product_tmpl_id
                if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                    expiry_date = line.production_date_inline + timedelta(days=product_tmpl.production_to_expiry_days)
            
            lot_vals = {
                'lot_number': line.lot_number_inline or 'LOT-TBD',
                'quantity': line.quantity_produced,
                'production_date': line.production_date_inline or fields.Date.today(),
                'expiry_date': expiry_date,
                'notes': line.lot_notes_inline,
            }
            
            if len(line.lot_ids) == 1:
                # Update existing
                line.lot_ids[0].write(lot_vals)
            else:
                # Create new
                lot_vals['production_line_id'] = line.id
                self.env['dm.production.lot'].create(lot_vals)
    
    @api.constrains('production_date_inline', 'expiry_date_inline')
    def _check_inline_expiry_date(self):
        """Validate expiry date in inline mode"""
        for line in self:
            if line.production_date_inline and line.expiry_date_inline:
                if line.expiry_date_inline < line.production_date_inline:
                    raise ValidationError(_(
                        'Expiry date (%s) cannot be earlier than production date (%s)'
                    ) % (line.expiry_date_inline, line.production_date_inline))
    
    def action_open_lot_wizard(self):
        """Open lot management wizard"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manage Production Lots',
            'res_model': 'production.lot.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'production_line_id': self.id}
        }
    
    @api.depends('product_id', 'product_packaging_id', 'quantity_ordered', 'quantity_produced',
                 'product_id.effective_container_type_id')
    def _compute_container_info(self):
        """
        Calculate containers and TEU using same logic as dm.deal.line
        Mimics the 3-tier priority system
        """
        for line in self:
            # Get container type from product
            if line.product_id and hasattr(line.product_id, 'effective_container_type_id'):
                line.container_type_id = line.product_id.effective_container_type_id
            else:
                line.container_type_id = False
            
            # Calculate containers for ordered quantity
            line.containers_ordered = line._calculate_containers(line.quantity_ordered)
            
            # Calculate containers for produced quantity
            line.containers_produced = line._calculate_containers(line.quantity_produced)
            
            # Calculate TEU
            if line.container_type_id and hasattr(line.container_type_id, 'teu_factor'):
                teu_factor = line.container_type_id.teu_factor or 0.0
                line.teu_ordered = line.containers_ordered * teu_factor
                line.teu_produced = line.containers_produced * teu_factor
            else:
                line.teu_ordered = 0.0
                line.teu_produced = 0.0
    
    def _calculate_containers(self, quantity_packages):
        """
        Calculate containers for given quantity using 3-tier priority:
        1. From packaging hierarchy (cartons_per_container)
        2. From volume (CBM)
        3. From weight (kg)
        
        Mirrors logic from dm.deal.line._compute_containers_required
        """
        self.ensure_one()
        
        if not quantity_packages or quantity_packages == 0:
            return 0.0
        
        # Priority 1: From packaging hierarchy
        if (hasattr(self.product_id, 'cartons_per_container') and 
            self.product_id.cartons_per_container and
            self.product_id.cartons_per_container > 0):
            return quantity_packages / self.product_id.cartons_per_container
        
        # Priority 2: From volume
        if (self.product_packaging_id and 
            hasattr(self.product_packaging_id, 'packaging_volume_m3') and
            self.product_packaging_id.packaging_volume_m3 and
            self.container_type_id and
            hasattr(self.container_type_id, 'internal_volume') and
            self.container_type_id.internal_volume and
            self.container_type_id.internal_volume > 0):
            
            total_cbm = quantity_packages * self.product_packaging_id.packaging_volume_m3
            return total_cbm / self.container_type_id.internal_volume
        
        # Priority 3: From weight
        if (self.product_packaging_id and
            hasattr(self.product_packaging_id, 'packaging_net_weight') and
            self.product_packaging_id.packaging_net_weight and
            self.container_type_id and
            hasattr(self.container_type_id, 'max_payload') and
            self.container_type_id.max_payload and
            self.container_type_id.max_payload > 0):
            
            total_weight = quantity_packages * self.product_packaging_id.packaging_net_weight
            return total_weight / self.container_type_id.max_payload
        
        # No calculation possible
        return 0.0
    
    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    @api.constrains('quantity_produced')
    def _check_quantity_produced(self):
        """Cannot have negative produced quantity"""
        for line in self:
            if line.quantity_produced < 0:
                raise ValidationError(_(
                    'Produced quantity cannot be negative for line %s'
                ) % line.product_name)
    
    @api.constrains('deal_line_id', 'production_run_id')
    def _check_unique_deal_line(self):
        """Each deal line can only appear once per production run"""
        for line in self:
            duplicate = self.search([
                ('id', '!=', line.id),
                ('production_run_id', '=', line.production_run_id.id),
                ('deal_line_id', '=', line.deal_line_id.id)
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'Deal line %s already exists in production run %s'
                ) % (line.deal_line_id.product_id.name, line.production_run_id.name))
    
    _sql_constraints = [
        ('deal_line_pr_uniq',
         'UNIQUE(production_run_id, deal_line_id)',
         'Deal line must be unique per production run'),
    ]
    
    # ========================================================================
    # DISPLAY
    # ========================================================================
    
    def name_get(self):
        result = []
        for line in self:
            name = f"{line.production_run_id.name} - {line.product_name}"
            result.append((line.id, name))
        return result