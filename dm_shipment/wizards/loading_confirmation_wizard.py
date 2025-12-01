# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class LoadingConfirmationWizard(models.TransientModel):
    """Loading Confirmation Wizard - Sprint 3 Final + Subdeal Refactoring
    
    One-screen loading interface with inline lot entry.
    Updates subdeal milestones and states (cascades to deal automatically).
    """
    _name = 'loading.confirmation.wizard'
    _description = 'Loading Confirmation Wizard'
    
    # =========================================================================
    # HEADER
    # =========================================================================
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        required=True,
        readonly=True
    )
    
    container_ids = fields.Many2many(
        'dm.container',
        string='Containers',
        compute='_compute_containers',
        help='Containers in this shipment'
    )
    
    # =========================================================================
    # LOADING LINES
    # =========================================================================
    
    line_ids = fields.One2many(
        'loading.confirmation.wizard.line',
        'wizard_id',
        string='Loading Lines'
    )
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    
    total_containers = fields.Integer(
        compute='_compute_summary',
        string='Total Containers'
    )
    
    total_lines = fields.Integer(
        compute='_compute_summary',
        string='Total Lines'
    )
    
    lines_with_actuals = fields.Integer(
        compute='_compute_summary',
        string='Lines with Actuals'
    )
    
    completion_percentage = fields.Float(
        compute='_compute_summary',
        string='Completion %',
        digits=(5, 1)
    )
    
    has_over_capacity = fields.Boolean(
        compute='_compute_summary',
        string='Over Capacity Warning'
    )
    
    has_lot_mismatch = fields.Boolean(
        compute='_compute_summary',
        string='Lot Quantity Mismatch'
    )
    
    # =========================================================================
    # VGM TRACKING
    # =========================================================================
    
    vgm_ids = fields.One2many(
        'loading.confirmation.wizard.vgm',
        'wizard_id',
        string='VGM Records'
    )
    
    # =========================================================================
    # COMPUTED METHODS
    # =========================================================================
    
    @api.depends('shipment_id')
    def _compute_containers(self):
        for wizard in self:
            wizard.container_ids = wizard.shipment_id.container_ids
    
    @api.depends('line_ids', 'line_ids.quantity_loaded', 'line_ids.lot_quantity_match',
                 'shipment_id.container_ids', 'shipment_id.container_ids.is_over_capacity')
    def _compute_summary(self):
        for wizard in self:
            wizard.total_containers = len(wizard.shipment_id.container_ids)
            wizard.total_lines = len(wizard.line_ids)
            wizard.lines_with_actuals = len([l for l in wizard.line_ids if l.quantity_loaded > 0])
            
            if wizard.total_lines > 0:
                wizard.completion_percentage = (wizard.lines_with_actuals / wizard.total_lines) * 100
            else:
                wizard.completion_percentage = 0.0
            
            wizard.has_over_capacity = any(wizard.shipment_id.container_ids.mapped('is_over_capacity'))
            wizard.has_lot_mismatch = any(
                not line.lot_quantity_match and line.quantity_loaded > 0
                for line in wizard.line_ids
            )
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    @api.model
    def default_get(self, fields_list):
        """Initialize wizard with container lines from shipment"""
        res = super().default_get(fields_list)
        
        shipment_id = self.env.context.get('active_id')
        if not shipment_id:
            raise UserError(_('No shipment selected'))
        
        shipment = self.env['dm.shipment'].browse(shipment_id)
        
        if shipment.state != 'loading':
            raise UserError(_('Shipment must be in loading state. Current state: %s') % shipment.state)
        
        if not shipment.container_ids:
            raise UserError(_('No containers to load'))
        
        res['shipment_id'] = shipment_id
        
        # Create wizard lines from container lines
        lines = []
        for container in shipment.container_ids:
            for container_line in container.line_ids:
                # Initialize quantity_loaded from existing data
                deal_line = container_line.deal_line_id
                
                # Priority: 1) container line, 2) sum of lots, 3) zero
                if container_line.quantity_loaded > 0:
                    initial_qty = container_line.quantity_loaded
                elif deal_line.lot_ids:
                    initial_qty = sum(deal_line.lot_ids.mapped('quantity'))
                else:
                    initial_qty = 0.0
                
                lines.append((0, 0, {
                    'container_id': container.id,
                    'container_line_id': container_line.id,
                    'deal_line_id': deal_line.id,
                    'product_id': container_line.product_id.id,
                    'quantity_planned': container_line.quantity_planned,
                    'quantity_loaded': initial_qty,
                }))
        
        res['line_ids'] = lines
        
        # Create container detail & VGM records for each container
        vgm_lines = []
        for container in shipment.container_ids:
            vgm_lines.append((0, 0, {
                'container_id': container.id,
                # Pre-populate from existing container data
                'container_number': container.container_number or '',
                'seal_tags': [(6, 0, container.seal_tags.ids)] if container.seal_tags else [],
                'tracker_tags': [(6, 0, container.tracker_tags.ids)] if container.tracker_tags else [],
                'is_smart_container': container.is_smart_container,
                'vgm': container.vgm or 0.0,
            }))
        
        res['vgm_ids'] = vgm_lines
        
        return res
    
    def action_confirm_loading(self):
        """Confirm loading - update actuals, finalize stock, and progress state"""
        self.ensure_one()
        
        # Validation
        if not any(line.quantity_loaded > 0 for line in self.line_ids):
            raise UserError(_('Enter at least one loaded quantity before confirming'))
        
        # Check lot quantity mismatches
        if self.has_lot_mismatch:
            mismatched_lines = [
                line for line in self.line_ids 
                if not line.lot_quantity_match and line.quantity_loaded > 0
            ]
            if mismatched_lines:
                msg = _('Lot quantities do not match loaded quantities:\n\n')
                for line in mismatched_lines[:5]:
                    msg += _('• %s: Loaded %.3f, Lots total %.3f\n') % (
                        line.product_id.name,
                        line.quantity_loaded,
                        line.total_lot_quantity
                    )
                raise UserError(msg)
        
        # Warning for over-capacity
        if self.has_over_capacity:
            _logger.warning('Shipment %s has containers over capacity', self.shipment_id.name)
        
        # Update container lines with loaded quantities
        for line in self.line_ids:
            if line.quantity_loaded > 0:
                line.container_line_id.write({
                    'quantity_loaded': line.quantity_loaded
                })
                
                # Sync lots to container line
                if line.deal_line_id.lot_ids:
                    line.container_line_id.write({
                        'lot_ids': [(6, 0, line.deal_line_id.lot_ids.ids)]
                    })
                
                # Sync quantity_loaded to deal line (for stock finalization)
                line.deal_line_id.write({
                    'quantity_loaded': line.quantity_loaded
                })
        
        # Update container details and VGM
        for vgm_line in self.vgm_ids:
            container_vals = {}
            
            # Container identification
            if vgm_line.container_number:
                container_vals['container_number'] = vgm_line.container_number
            
            # Security details
            container_vals['seal_tags'] = [(6, 0, vgm_line.seal_tags.ids)]
            container_vals['tracker_tags'] = [(6, 0, vgm_line.tracker_tags.ids)]
            container_vals['is_smart_container'] = vgm_line.is_smart_container
            
            # VGM
            if vgm_line.vgm > 0:
                container_vals['vgm'] = vgm_line.vgm
                container_vals['vgm_declaration_date'] = fields.Date.today()
            
            if container_vals:
                vgm_line.container_id.write(container_vals)
        
        # Collect affected subdeals and update them
        affected_subdeals = self.env['dm.deal.subdeal']
        for line in self.line_ids:
            if line.quantity_loaded > 0 and line.deal_line_id.subdeal_id:
                affected_subdeals |= line.deal_line_id.subdeal_id
        
        # Update each affected subdeal: milestone, state, stock finalization
        for subdeal in affected_subdeals:
            # Update loading milestone
            subdeal.write({'loading_actual': fields.Date.today()})
            
            # Finalize stock documents (SO delivery, PO receipt)
            try:
                subdeal.action_finalize_shipment()
            except Exception as e:
                _logger.warning(
                    f"Failed to finalize stock for subdeal {subdeal.id}: {e}"
                )
            
            # Progress subdeal state via workflow method
            if hasattr(subdeal, 'action_mark_shipped'):
                subdeal.action_mark_shipped()
            elif subdeal.state in ['confirmed', 'in_production', 'ready']:
                subdeal.write({'state': 'shipped'})
            
            _logger.info(
                f"Subdeal {subdeal.id} (Deal: {subdeal.deal_id.name}) "
                f"loading confirmed, stock finalized, marked shipped"
            )
        
        # Progress shipment state to 'loaded'
        self.shipment_id.write({'state': 'loaded'})
        
        # Log summary to shipment
        total_loaded = sum(line.quantity_loaded for line in self.line_ids)
        total_planned = sum(line.quantity_planned for line in self.line_ids)
        
        self.shipment_id.message_post(
            body=_(
                '<b>📦 Loading Confirmed</b><br/><br/>'
                'Total Loaded: %.2f packages<br/>'
                'Total Planned: %.2f packages<br/>'
                'Variance: %.2f packages (%.1f%%)<br/>'
                'Sub-deals Updated: %d'
            ) % (
                total_loaded,
                total_planned,
                total_loaded - total_planned,
                ((total_loaded - total_planned) / total_planned * 100) if total_planned else 0,
                len(affected_subdeals)
            ),
            subject=_('Loading Confirmed'),
            message_type='notification'
        )
        
        # Return to shipment form
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shipment: %s') % self.shipment_id.name,
            'res_model': 'dm.shipment',
            'res_id': self.shipment_id.id,
            'view_mode': 'form',
            'target': 'current'
        }


class LoadingConfirmationWizardLine(models.TransientModel):
    """Loading wizard line - per container line"""
    _name = 'loading.confirmation.wizard.line'
    _description = 'Loading Confirmation Line'
    
    wizard_id = fields.Many2one(
        'loading.confirmation.wizard',
        required=True,
        ondelete='cascade'
    )
    
    # =========================================================================
    # REFERENCES
    # =========================================================================
    
    container_id = fields.Many2one(
        'dm.container',
        string='Container',
        required=True
    )
    
    container_line_id = fields.Many2one(
        'dm.container.line',
        string='Container Line',
        required=True
    )
    
    deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        required=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    
    # =========================================================================
    # DISPLAY HELPERS
    # =========================================================================
    
    container_number = fields.Char(
        string='Container #',
        compute='_compute_container_number',
        help='Container number from Containers & VGM tab'
    )

    @api.depends('wizard_id.vgm_ids', 'wizard_id.vgm_ids.container_id', 
                 'wizard_id.vgm_ids.container_number', 'container_id')
    def _compute_container_number(self):
        """Get container number from VGM wizard line (live update across tabs)"""
        for line in self:
            container_number = ''
            if line.wizard_id and line.container_id:
                # Find matching VGM line for this container
                vgm_line = line.wizard_id.vgm_ids.filtered(
                    lambda v: v.container_id == line.container_id
                )
                if vgm_line:
                    container_number = vgm_line[0].container_number or ''
            # Fallback to actual container record if no wizard value
            if not container_number and line.container_id:
                container_number = line.container_id.container_number or ''
            line.container_number = container_number
    
    container_type = fields.Char(
        related='container_id.container_type_id.name',
        string='Type'
    )
    
    packaging_name = fields.Char(
        related='deal_line_id.product_packaging_id.name',
        string='Packaging'
    )
    
    product_packaging_id = fields.Many2one(
        related='deal_line_id.product_packaging_id',
        string='Packaging'
    )

    has_variance = fields.Boolean(
        string='Has Variance',
        compute='_compute_variance',
        help='True if loaded differs from planned'
    )    
    
    # =========================================================================
    # QUANTITIES
    # =========================================================================
    
    quantity_planned = fields.Float(
        string='Planned (Pkg)',
        digits=(16, 3),
        readonly=True
    )
    
    quantity_loaded = fields.Float(
        string='Loaded (Pkg)',
        digits=(16, 3)
    )
    
    quantity_variance = fields.Float(
        string='Variance',
        compute='_compute_variance',
        digits=(16, 3)
    )
    
    variance_percentage = fields.Float(
        string='Var %',
        compute='_compute_variance',
        digits=(5, 1)
    )
    
    @api.depends('quantity_planned', 'quantity_loaded')
    def _compute_variance(self):
        for line in self:
            line.quantity_variance = line.quantity_loaded - line.quantity_planned
            if line.quantity_planned > 0:
                line.variance_percentage = (line.quantity_variance / line.quantity_planned) * 100
            else:
                line.variance_percentage = 0.0
            # Add has_variance computation
            line.has_variance = abs(line.quantity_variance) > 0.001
    
    # =========================================================================
    # LOT INLINE EDITING (SINGLE LOT FAST ENTRY)
    # =========================================================================
    
    lot_number_inline = fields.Char(
        string='Lot #',
        compute='_compute_lot_inline',
        inverse='_inverse_lot_number',
        store=False,
        help='Lot number (editable for single lot) or "Multiple (N)" if multiple lots'
    )
    
    production_date_inline = fields.Date(
        string='Prod Date',
        compute='_compute_lot_inline',
        inverse='_inverse_production_date',
        store=False,
        help='Production date (editable for single lot) or "Various" if multiple lots'
    )
    
    expiry_date_inline = fields.Date(
        string='Expiry',
        compute='_compute_lot_inline',
        inverse='_inverse_expiry_date',
        store=False,
        help='Expiry date (auto-calculated) or "Various" if multiple lots'
    )
    
    # =========================================================================
    # LOT SUMMARY (READONLY INFO)
    # =========================================================================
    
    lot_count = fields.Integer(
        string='# Lots',
        compute='_compute_lot_info'
    )
    
    total_lot_quantity = fields.Float(
        string='Total Lot Qty',
        compute='_compute_lot_info',
        digits=(16, 3)
    )
    
    lot_quantity_match = fields.Boolean(
        string='Lots Match',
        compute='_compute_lot_info',
        help='True if total lot quantity matches loaded quantity'
    )
    
    # =========================================================================
    # LOT INLINE COMPUTED/INVERSE
    # =========================================================================
    
    @api.depends('deal_line_id', 'deal_line_id.lot_ids', 
                 'deal_line_id.lot_ids.lot_number',
                 'deal_line_id.lot_ids.production_date',
                 'deal_line_id.lot_ids.expiry_date')
    def _compute_lot_inline(self):
        """Compute inline lot fields from deal line lots"""
        for line in self:
            lots = line.deal_line_id.lot_ids
            
            if not lots:
                line.lot_number_inline = ''
                line.production_date_inline = False
                line.expiry_date_inline = False
            elif len(lots) == 1:
                # Single lot - show actual values
                lot = lots[0]
                line.lot_number_inline = lot.lot_number or ''
                line.production_date_inline = lot.production_date
                line.expiry_date_inline = lot.expiry_date
            else:
                # Multiple lots - show indicators
                line.lot_number_inline = f'Multiple ({len(lots)})'
                line.production_date_inline = False  # Will display as "Various" in view
                line.expiry_date_inline = False
    
    def _inverse_lot_number(self):
        """Create or update lot when lot number entered inline"""
        for line in self:
            if not line.lot_number_inline or line.lot_number_inline.startswith('Multiple'):
                continue
            
            lots = line.deal_line_id.lot_ids
            
            if len(lots) == 0:
                # Create new lot
                self.env['dm.deal.line.lot'].create({
                    'deal_line_id': line.deal_line_id.id,
                    'lot_number': line.lot_number_inline,
                    'quantity': line.quantity_loaded,
                    'production_date': fields.Date.today(),
                })
            elif len(lots) == 1:
                # Update existing single lot
                lots[0].write({
                    'lot_number': line.lot_number_inline,
                    'quantity': line.quantity_loaded,
                })
    
    def _inverse_production_date(self):
        """Update production date on single lot"""
        for line in self:
            if not line.production_date_inline:
                continue
            
            lots = line.deal_line_id.lot_ids
            
            if len(lots) == 1:
                lots[0].write({'production_date': line.production_date_inline})
            elif len(lots) == 0 and line.lot_number_inline:
                # Create lot with production date
                self.env['dm.deal.line.lot'].create({
                    'deal_line_id': line.deal_line_id.id,
                    'lot_number': line.lot_number_inline or 'LOT-1',
                    'quantity': line.quantity_loaded,
                    'production_date': line.production_date_inline,
                })
    
    def _inverse_expiry_date(self):
        """Update expiry date on single lot"""
        for line in self:
            if not line.expiry_date_inline:
                continue
            
            lots = line.deal_line_id.lot_ids
            
            if len(lots) == 1:
                lots[0].write({'expiry_date': line.expiry_date_inline})
    
    @api.onchange('production_date_inline', 'product_id')
    def _onchange_production_date_inline(self):
        """Auto-calculate expiry date from production date + shelf life"""
        for line in self:
            if line.production_date_inline and line.product_id:
                product_tmpl = line.product_id.product_tmpl_id
                if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                    line.expiry_date_inline = line.production_date_inline + timedelta(
                        days=product_tmpl.production_to_expiry_days
                    )
    
    # =========================================================================
    # LOT INFO SUMMARY
    # =========================================================================
    
    @api.depends('deal_line_id', 'deal_line_id.lot_ids', 'deal_line_id.lot_ids.quantity', 'quantity_loaded')
    def _compute_lot_info(self):
        """Compute lot summary info"""
        for line in self:
            lots = line.deal_line_id.lot_ids
            
            line.lot_count = len(lots)
            line.total_lot_quantity = sum(lots.mapped('quantity'))
            
            # Check if lot quantities match loaded quantity
            if line.quantity_loaded > 0:
                line.lot_quantity_match = abs(line.total_lot_quantity - line.quantity_loaded) < 0.001
            else:
                line.lot_quantity_match = True
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def action_manage_lots(self):
        """Open simplified lot wizard for loading context"""
        self.ensure_one()
        
        # Create loading-specific lot wizard
        wizard = self.env['loading.lot.wizard'].create({
            'loading_wizard_line_id': self.id,
            'deal_line_id': self.deal_line_id.id,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manage Lots: %s') % self.product_id.name,
            'res_model': 'loading.lot.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',  # This should make close return to parent
        }


class LoadingConfirmationWizardVGM(models.TransientModel):
    """Container details and VGM tracking per container
    
    Extended to capture container identification and security details
    during loading confirmation (Issue 2 fix).
    """
    _name = 'loading.confirmation.wizard.vgm'
    _description = 'Container Details & VGM Record'
    
    wizard_id = fields.Many2one(
        'loading.confirmation.wizard',
        required=True,
        ondelete='cascade'
    )
    
    container_id = fields.Many2one(
        'dm.container',
        string='Container',
        required=True
    )
    
    # =========================================================================
    # CONTAINER IDENTIFICATION
    # =========================================================================
    
    container_number = fields.Char(
        string='Container #',
        help='ISO 6346 format: 4 letters + 7 digits (e.g. ABCD1234567)'
    )
    
    container_type = fields.Char(
        related='container_id.container_type_id.name',
        string='Type',
        readonly=True
    )
    
    # =========================================================================
    # SECURITY: SEALS & TRACKERS
    # =========================================================================
    
    seal_tags = fields.Many2many(
        'dm.container.seal',
        'loading_wizard_vgm_seal_rel',
        'vgm_id',
        'seal_id',
        string='Seals',
        help='Security seals applied to container'
    )
    
    tracker_tags = fields.Many2many(
        'dm.container.tracker',
        'loading_wizard_vgm_tracker_rel',
        'vgm_id',
        'tracker_id',
        string='Trackers',
        help='GPS/temperature tracking devices'
    )
    
    is_smart_container = fields.Boolean(
        string='Smart Container',
        help='Has IoT tracking capabilities'
    )
    
    # =========================================================================
    # VGM (EXISTING)
    # =========================================================================
    
    planned_weight = fields.Float(
        related='container_id.planned_weight',
        string='Planned Weight (kg)',
        digits=(16, 2)
    )
    
    vgm = fields.Float(
        string='VGM (kg)',
        digits=(16, 2),
        help='Verified Gross Mass'
    )
    
    vgm_variance = fields.Float(
        string='Variance (kg)',
        compute='_compute_vgm_variance',
        digits=(16, 2)
    )
    
    @api.depends('planned_weight', 'vgm')
    def _compute_vgm_variance(self):
        for record in self:
            record.vgm_variance = record.vgm - record.planned_weight
    
    # =========================================================================
    # PERSISTENCE: SYNC TO ACTUAL CONTAINER ON SAVE
    # =========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        """Persist container details to actual container on wizard line creation"""
        records = super().create(vals_list)
        
        for record in records:
            if not record.container_id:
                continue
            
            container_vals = {}
            
            if record.container_number:
                container_vals['container_number'] = record.container_number
            
            if record.seal_tags:
                container_vals['seal_tags'] = [(6, 0, record.seal_tags.ids)]
            
            if record.tracker_tags:
                container_vals['tracker_tags'] = [(6, 0, record.tracker_tags.ids)]
            
            if record.is_smart_container:
                container_vals['is_smart_container'] = record.is_smart_container
            
            if record.vgm > 0:
                container_vals['vgm'] = record.vgm
                container_vals['vgm_declaration_date'] = fields.Date.today()
            
            if container_vals:
                record.container_id.write(container_vals)
        
        return records
    
    def write(self, vals):
        """Persist container details to actual container on wizard save"""
        res = super().write(vals)
        
        # Fields that should sync to dm.container
        sync_fields = {'container_number', 'seal_tags', 'tracker_tags', 'is_smart_container', 'vgm'}
        
        # Only sync if any of the tracked fields changed
        if sync_fields & set(vals.keys()):
            for record in self:
                if not record.container_id:
                    continue
                    
                container_vals = {}
                
                # Container identification
                if 'container_number' in vals:
                    container_vals['container_number'] = record.container_number
                
                # Security details
                if 'seal_tags' in vals:
                    container_vals['seal_tags'] = [(6, 0, record.seal_tags.ids)]
                
                if 'tracker_tags' in vals:
                    container_vals['tracker_tags'] = [(6, 0, record.tracker_tags.ids)]
                
                if 'is_smart_container' in vals:
                    container_vals['is_smart_container'] = record.is_smart_container
                
                # VGM
                if 'vgm' in vals and record.vgm > 0:
                    container_vals['vgm'] = record.vgm
                    container_vals['vgm_declaration_date'] = fields.Date.today()
                
                if container_vals:
                    record.container_id.write(container_vals)
        
        return res