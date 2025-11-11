# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmShipmentAllocationWizard(models.TransientModel):
    """
    Shipment Allocation Wizard - Sprint 1
    
    Validates production runs and creates/updates shipments with:
    - Hard validation (blocks): Different suppliers/vendors
    - Soft validation (warns): Mixed routes, mixed dates
    - Route override capability
    - Date strategy selection
    """
    _name = 'dm.shipment.allocation.wizard'
    _description = 'Allocate Production Runs to Shipment'
    
    # ========================================================================
    # CORE FIELDS
    # ========================================================================
    
    production_run_ids = fields.Many2many(
        'dm.production.run',
        string='Production Runs',
        required=True,
        help='PRs to allocate to shipment'
    )
    
    shipment_mode = fields.Selection([
        ('new', 'Create New Shipment'),
        ('existing', 'Add to Existing Shipment'),
    ], string='Shipment Mode',
       default='new',
       required=True)
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Existing Shipment',
        domain="[('state', 'in', ['draft', 'confirmed'])]",
        help='Select existing shipment to add PRs to'
    )
    
    # ========================================================================
    # VALIDATION STATUS
    # ========================================================================
    
    has_hard_errors = fields.Boolean(
        compute='_compute_validation_status',
        string='Has Blocking Errors',
        help='Hard validation failures that prevent allocation'
    )
    
    has_soft_warnings = fields.Boolean(
        compute='_compute_validation_status',
        string='Has Warnings',
        help='Soft validation warnings that can be overridden'
    )
    
    validation_summary = fields.Html(
        compute='_compute_validation_status',
        string='Validation Results'
    )
    
    # Hard validation results
    supplier_conflict = fields.Boolean(
        compute='_compute_validation_status',
        help='Different suppliers across PRs'
    )
    
    vendor_conflict = fields.Boolean(
        compute='_compute_validation_status',
        help='Different vendors across PRs'
    )
    
    already_allocated_conflict = fields.Boolean(
        compute='_compute_validation_status',
        help='Some PRs already allocated (new shipment mode)'
    )
    
    # Soft validation results
    mixed_loading_ports = fields.Boolean(
        compute='_compute_validation_status',
        help='Different loading ports across deals'
    )
    
    mixed_discharge_ports = fields.Boolean(
        compute='_compute_validation_status',
        help='Different discharge ports across deals'
    )
    
    mixed_rts_dates = fields.Boolean(
        compute='_compute_validation_status',
        help='RTS dates vary by more than 7 days'
    )
    
    # ========================================================================
    # OVERRIDE FIELDS
    # ========================================================================
    
    use_route_override = fields.Boolean(
        string='Override Route',
        default=False,
        help='Manually select ports when mixed routes detected'
    )
    
    loading_port_id = fields.Many2one(
        'dm.port',
        string='Loading Port',
        help='Override loading port (when mixed)'
    )
    
    discharge_port_id = fields.Many2one(
        'dm.port',
        string='Discharge Port',
        help='Override discharge port (when mixed)'
    )
    
    loading_date_strategy = fields.Selection([
        ('earliest', 'Use Earliest RTS Date'),
        ('latest', 'Use Latest RTS Date'),
        ('manual', 'Manual Date Selection'),
    ], string='Date Strategy',
       default='earliest',
       help='How to determine shipment loading date when RTS dates vary'
    )
    
    loading_date_manual = fields.Date(
        string='Manual Loading Date',
        help='Manually selected loading date'
    )
    
    # ========================================================================
    # COMPUTED VALIDATION
    # ========================================================================
    
    @api.depends('production_run_ids', 'shipment_mode', 'shipment_id',
                 'use_route_override', 'loading_port_id', 'discharge_port_id')
    def _compute_validation_status(self):
        """
        Validate PRs and generate status summary.
        
        Hard Validations (Block):
        - Different suppliers
        - Different vendors
        - PRs already allocated (if mode='new')
        
        Soft Validations (Warn):
        - Mixed loading ports
        - Mixed discharge ports
        - RTS dates vary >7 days
        """
        for wizard in self:
            if not wizard.production_run_ids:
                wizard.has_hard_errors = False
                wizard.has_soft_warnings = False
                wizard.validation_summary = '<p>No production runs selected.</p>'
                continue
            
            prs = wizard.production_run_ids
            deals = prs.mapped('deal_ids')
            
            # Initialize validation flags
            hard_errors = []
            soft_warnings = []
            
            # ================================================================
            # HARD VALIDATION 1: Same Supplier
            # ================================================================
            suppliers = prs.mapped('supplier_id')
            wizard.supplier_conflict = len(suppliers) > 1
            
            if wizard.supplier_conflict:
                supplier_list = '<br/>'.join([
                    f"  • {pr.name}: {pr.supplier_id.name}"
                    for pr in prs
                ])
                hard_errors.append(
                    f"<strong>❌ Different Suppliers</strong><br/>"
                    f"All PRs must have the same supplier:<br/>{supplier_list}"
                )
            
            # ================================================================
            # HARD VALIDATION 2: Same Vendor (from deals)
            # ================================================================
            vendors = deals.mapped('supplier_id').filtered(lambda v: v)
            wizard.vendor_conflict = len(vendors) > 1
            
            if wizard.vendor_conflict:
                vendor_list = '<br/>'.join([
                    f"  • {deal.name}: {deal.supplier_id.name}"
                    for deal in deals if deal.supplier_id
                ])
                hard_errors.append(
                    f"<strong>❌ Different Vendors</strong><br/>"
                    f"All deals must have the same vendor:<br/>{vendor_list}"
                )
            
            # ================================================================
            # HARD VALIDATION 3: Not Already Allocated (new shipment mode)
            # ================================================================
            wizard.already_allocated_conflict = False
            if wizard.shipment_mode == 'new':
                allocated_prs = prs.filtered('shipment_allocated')
                wizard.already_allocated_conflict = bool(allocated_prs)
                
                if wizard.already_allocated_conflict:
                    allocated_list = '<br/>'.join([
                        f"  • {pr.name}: Already in {pr.shipment_count} shipment(s)"
                        for pr in allocated_prs
                    ])
                    hard_errors.append(
                        f"<strong>❌ PRs Already Allocated</strong><br/>"
                        f"Cannot create new shipment with already-allocated PRs:<br/>"
                        f"{allocated_list}<br/>"
                        f"<em>Use 'Add to Existing Shipment' mode instead.</em>"
                    )
            
            # ================================================================
            # SOFT VALIDATION 1: Mixed Loading Ports
            # ================================================================
            loading_ports = deals.mapped('loading_port_id')
            wizard.mixed_loading_ports = len(loading_ports) > 1
            
            if wizard.mixed_loading_ports and not wizard.use_route_override:
                port_list = '<br/>'.join([
                    f"  • {deal.name}: {deal.loading_port_id.name}"
                    for deal in deals
                ])
                soft_warnings.append(
                    f"<strong>⚠️ Mixed Loading Ports</strong><br/>"
                    f"{port_list}<br/>"
                    f"<em>Enable 'Override Route' to select port manually.</em>"
                )
            
            # ================================================================
            # SOFT VALIDATION 2: Mixed Discharge Ports
            # ================================================================
            discharge_ports = deals.mapped('discharge_port_id')
            wizard.mixed_discharge_ports = len(discharge_ports) > 1
            
            if wizard.mixed_discharge_ports and not wizard.use_route_override:
                port_list = '<br/>'.join([
                    f"  • {deal.name}: {deal.discharge_port_id.name}"
                    for deal in deals
                ])
                soft_warnings.append(
                    f"<strong>⚠️ Mixed Discharge Ports</strong><br/>"
                    f"{port_list}<br/>"
                    f"<em>Enable 'Override Route' to select port manually.</em>"
                )
            
            # ================================================================
            # SOFT VALIDATION 3: Mixed RTS Dates (>7 days variance)
            # ================================================================
            rts_dates = prs.mapped('rts_current')
            wizard.mixed_rts_dates = False
            
            if rts_dates:
                min_date = min(rts_dates)
                max_date = max(rts_dates)
                date_diff = (max_date - min_date).days
                
                wizard.mixed_rts_dates = date_diff > 7
                
                if wizard.mixed_rts_dates:
                    date_list = '<br/>'.join([
                        f"  • {pr.name}: {pr.rts_current.strftime('%Y-%m-%d')}"
                        for pr in prs
                    ])
                    soft_warnings.append(
                        f"<strong>⚠️ Mixed RTS Dates</strong><br/>"
                        f"RTS dates vary by {date_diff} days:<br/>"
                        f"{date_list}<br/>"
                        f"<em>Select date strategy below.</em>"
                    )
            
            # ================================================================
            # SET FLAGS
            # ================================================================
            wizard.has_hard_errors = bool(hard_errors)
            wizard.has_soft_warnings = bool(soft_warnings)
            
            # ================================================================
            # BUILD SUMMARY HTML
            # ================================================================
            summary_parts = []
            
            if hard_errors:
                summary_parts.append(
                    '<div class="alert alert-danger">'
                    '<h4>❌ Blocking Errors</h4>'
                    + '<br/><br/>'.join(hard_errors) +
                    '</div>'
                )
            
            if soft_warnings:
                summary_parts.append(
                    '<div class="alert alert-warning">'
                    '<h4>⚠️ Warnings (Can Override)</h4>'
                    + '<br/><br/>'.join(soft_warnings) +
                    '</div>'
                )
            
            if not hard_errors and not soft_warnings:
                summary_parts.append(
                    '<div class="alert alert-success">'
                    '<h4>✅ Validation Passed</h4>'
                    f'<p>{len(prs)} production run(s) ready for allocation.</p>'
                    '</div>'
                )
            
            wizard.validation_summary = ''.join(summary_parts)
    
    # ========================================================================
    # ALLOCATION ACTION
    # ========================================================================
    
    def action_allocate(self):
        """
        Allocate production runs to shipment.
        
        Creates new shipment or adds to existing based on mode.
        Applies route overrides and date strategy if configured.
        """
        self.ensure_one()
        
        # Final validation check
        if self.has_hard_errors:
            raise UserError(_(
                'Cannot allocate: Hard validation errors detected.\n\n'
                'Please resolve blocking issues before proceeding.'
            ))
        
        # Validate route override if enabled
        if self.use_route_override:
            if not self.loading_port_id or not self.discharge_port_id:
                raise UserError(_(
                    'Route override enabled but ports not selected.\n\n'
                    'Please select both loading and discharge ports.'
                ))
        
        # Validate manual date if selected
        if self.loading_date_strategy == 'manual' and not self.loading_date_manual:
            raise UserError(_(
                'Manual date strategy selected but no date provided.\n\n'
                'Please select a loading date.'
            ))
        
        # ====================================================================
        # CREATE OR UPDATE SHIPMENT
        # ====================================================================
        
        if self.shipment_mode == 'new':
            shipment = self._create_new_shipment()
        else:
            shipment = self.shipment_id
            if not shipment:
                raise UserError(_('Please select an existing shipment.'))
        
        # ====================================================================
        # ADD PRODUCTION RUNS
        # ====================================================================
        
        shipment.production_run_ids = [(4, pr.id) for pr in self.production_run_ids]
        
        # ====================================================================
        # LOG ALLOCATION
        # ====================================================================
        
        _logger.info(
            f"Allocated {len(self.production_run_ids)} PRs to shipment {shipment.name}: "
            f"{', '.join(self.production_run_ids.mapped('name'))}"
        )
        
        shipment.message_post(
            body=_(
                'Production runs allocated:<br/>'
                '%s'
            ) % '<br/>'.join([
                f"• {pr.name}" for pr in self.production_run_ids
            ]),
            subject=_('PRs Allocated')
        )
        
        # ====================================================================
        # RETURN ACTION
        # ====================================================================
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shipment'),
            'res_model': 'dm.shipment',
            'res_id': shipment.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _create_new_shipment(self):
        """
        Create new shipment with route and date from PRs/deals.
        
        Applies overrides if configured.
        """
        deals = self.production_run_ids.mapped('deal_ids')
        
        # Determine ports
        if self.use_route_override:
            loading_port = self.loading_port_id
            discharge_port = self.discharge_port_id
        else:
            # Use first deal's ports (validation ensures consistency)
            loading_port = deals[0].loading_port_id if deals else False
            discharge_port = deals[0].discharge_port_id if deals else False
        
        # Determine loading date
        loading_date = self._determine_loading_date()
        
        # Create shipment
        shipment = self.env['dm.shipment'].create({
            'loading_port_id': loading_port.id,
            'discharge_port_id': discharge_port.id,
            'loading_date': loading_date,
            'state': 'draft',
        })
        
        _logger.info(
            f"Created shipment {shipment.name}: "
            f"{loading_port.name} → {discharge_port.name}, "
            f"Loading: {loading_date}"
        )
        
        return shipment
    
    def _determine_loading_date(self):
        """
        Determine shipment loading date based on strategy.
        
        Strategies:
        - earliest: Use earliest RTS date from PRs
        - latest: Use latest RTS date from PRs
        - manual: Use manually selected date
        """
        if self.loading_date_strategy == 'manual':
            return self.loading_date_manual
        
        rts_dates = self.production_run_ids.mapped('rts_current')
        
        if not rts_dates:
            return fields.Date.today()
        
        if self.loading_date_strategy == 'earliest':
            return min(rts_dates)
        else:  # latest
            return max(rts_dates)