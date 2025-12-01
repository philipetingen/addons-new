# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class ShipmentAllocationWizard(models.TransientModel):
    """Wizard for allocating deals to shipment with validation and date strategy
    
    User selects deals; wizard accesses primary_subdeal_id for allocation.
    Subdeals are the primary allocation target; deals updated via cascade.
    Proposed dates are editable and stored on shipment at creation.
    """
    _name = 'shipment.allocation.wizard'
    _description = 'Shipment Allocation Wizard'
    
    # =========================================================================
    # INPUT
    # =========================================================================
    
    deal_ids = fields.Many2many(
        'dm.deal',
        'shipment_alloc_wizard_deal_rel',
        'wizard_id',
        'deal_id',
        string='Deals to Allocate',
        required=True
    )
    
    # =========================================================================
    # VALIDATIONS (COMPUTED)
    # =========================================================================
    
    has_hard_errors = fields.Boolean(
        compute='_compute_validations',
        string='Has Blocking Errors'
    )
    
    hard_errors = fields.Html(
        compute='_compute_validations',
        string='Blocking Errors'
    )
    
    has_soft_warnings = fields.Boolean(
        compute='_compute_validations',
        string='Has Warnings'
    )
    
    soft_warnings = fields.Html(
        compute='_compute_validations',
        string='Warnings (Can Override)'
    )
    
    # =========================================================================
    # ROUTE OVERRIDE
    # =========================================================================
    
    route_consistent = fields.Boolean(
        compute='_compute_route_consistency',
        string='Route Consistent'
    )
    
    use_route_override = fields.Boolean(
        string='Override Route',
        default=False,
        help='Manually specify loading/discharge ports'
    )
    
    loading_port_id = fields.Many2one(
        'dm.port',
        string='Loading Port (POL)',
        help='Override loading port for shipment'
    )
    
    discharge_port_id = fields.Many2one(
        'dm.port',
        string='Discharge Port (POD)',
        help='Override discharge port for shipment'
    )
    
    # =========================================================================
    # DATE STRATEGY
    # =========================================================================
    
    date_strategy = fields.Selection([
        ('earliest_earliest', 'Conservative: Start Early / Finish Early'),
        ('earliest_latest', 'Mixed: Start Early / Finish Late'),
        ('latest_latest', 'Aggressive: Start Late / Finish Late'),
        ('manual', 'Manual Entry')
    ], string='Date Strategy',
        default='earliest_latest',
        required=True,
        help='How to calculate shipment milestone dates from deal dates'
    )
    
    # Manual date entry (used when strategy = 'manual')
    loading_date_manual = fields.Date(
        string='Loading Date (Manual)'
    )
    
    etd_manual = fields.Date(
        string='ETD (Manual)'
    )
    
    eta_manual = fields.Date(
        string='ETA (Manual)'
    )
    
    delivery_manual = fields.Date(
        string='Delivery (Manual)'
    )
    
    # =========================================================================
    # PROPOSED DATES (Editable with defaults from strategy)
    # =========================================================================
    
    proposed_loading = fields.Date(
        string='Proposed Loading Date',
        help='Editable - will be stored on shipment'
    )
    
    proposed_etd = fields.Date(
        string='Proposed ETD',
        help='Editable - will be stored on shipment'
    )
    
    proposed_eta = fields.Date(
        string='Proposed ETA',
        help='Editable - will be stored on shipment'
    )
    
    proposed_delivery = fields.Date(
        string='Proposed Delivery',
        help='Editable - will be stored on shipment'
    )
    
    @api.model
    def default_get(self, fields_list):
        """Set proposed dates based on deal_ids from context"""
        res = super().default_get(fields_list)
        
        # Get deal_ids from context (passed from action)
        active_ids = self.env.context.get('active_ids', [])
        active_model = self.env.context.get('active_model')
        
        if active_model == 'dm.deal' and active_ids:
            deals = self.env['dm.deal'].browse(active_ids)
            res['deal_ids'] = [(6, 0, active_ids)]
            
            # Calculate default dates using earliest_latest strategy
            loading_dates = [d.loading_current for d in deals if d.loading_current]
            etd_dates = [d.etd_current for d in deals if d.etd_current]
            eta_dates = [d.eta_current for d in deals if d.eta_current]
            delivery_dates = [d.delivery_current for d in deals if d.delivery_current]
            
            # Default strategy: earliest_latest
            res['proposed_loading'] = min(loading_dates) if loading_dates else False
            res['proposed_etd'] = min(etd_dates) if etd_dates else False
            res['proposed_eta'] = max(eta_dates) if eta_dates else False
            res['proposed_delivery'] = max(delivery_dates) if delivery_dates else False
        
        return res
    
    @api.onchange('deal_ids', 'date_strategy', 'loading_date_manual', 'etd_manual', 
                  'eta_manual', 'delivery_manual')
    def _onchange_compute_proposed_dates(self):
        """Recalculate proposed dates when strategy or deals change"""
        if self.date_strategy == 'manual':
            self.proposed_loading = self.loading_date_manual
            self.proposed_etd = self.etd_manual
            self.proposed_eta = self.eta_manual
            self.proposed_delivery = self.delivery_manual
            return
        
        if not self.deal_ids:
            return  # Don't clear - keep existing values
        
        # Collect dates from deals
        loading_dates = [d.loading_current for d in self.deal_ids if d.loading_current]
        etd_dates = [d.etd_current for d in self.deal_ids if d.etd_current]
        eta_dates = [d.eta_current for d in self.deal_ids if d.eta_current]
        delivery_dates = [d.delivery_current for d in self.deal_ids if d.delivery_current]
        
        if self.date_strategy == 'earliest_earliest':
            self.proposed_loading = min(loading_dates) if loading_dates else False
            self.proposed_etd = min(etd_dates) if etd_dates else False
            self.proposed_eta = min(eta_dates) if eta_dates else False
            self.proposed_delivery = min(delivery_dates) if delivery_dates else False
        
        elif self.date_strategy == 'earliest_latest':
            self.proposed_loading = min(loading_dates) if loading_dates else False
            self.proposed_etd = min(etd_dates) if etd_dates else False
            self.proposed_eta = max(eta_dates) if eta_dates else False
            self.proposed_delivery = max(delivery_dates) if delivery_dates else False
        
        elif self.date_strategy == 'latest_latest':
            self.proposed_loading = max(loading_dates) if loading_dates else False
            self.proposed_etd = max(etd_dates) if etd_dates else False
            self.proposed_eta = max(eta_dates) if eta_dates else False
            self.proposed_delivery = max(delivery_dates) if delivery_dates else False
    
    # =========================================================================
    # DATE IMPACT MATRIX
    # =========================================================================
    
    date_strategy_line_ids = fields.One2many(
        'shipment.allocation.date.strategy.line',
        'wizard_id',
        string='Date Impact by Deal',
        compute='_compute_date_impact_lines',
        store=True
    )
    
    # =========================================================================
    # VALIDATION LOGIC
    # =========================================================================
    
    @api.depends('deal_ids', 'deal_ids.supplier_id', 'deal_ids.primary_subdeal_id.shipment_allocated', 'deal_ids.state')
    def _compute_validations(self):
        """Compute hard errors and soft warnings"""
        for wizard in self:
            hard_errors_list = []
            soft_warnings_list = []
            
            if not wizard.deal_ids:
                wizard.has_hard_errors = True
                wizard.hard_errors = '<p><b>No deals selected</b></p>'
                wizard.has_soft_warnings = False
                wizard.soft_warnings = ''
                continue
            
            # HARD ERROR 1: Different suppliers
            suppliers = wizard.deal_ids.mapped('supplier_id')
            if len(suppliers) > 1:
                supplier_names = ', '.join(suppliers.mapped('name'))
                hard_errors_list.append(
                    f'<li><b>Multiple suppliers:</b> {supplier_names}</li>'
                )
            
            # HARD ERROR 2: Already allocated subdeals
            allocated_deals = []
            for deal in wizard.deal_ids:
                if deal.primary_subdeal_id and deal.primary_subdeal_id.shipment_allocated:
                    allocated_deals.append(deal)
            
            if allocated_deals:
                deal_names = ', '.join([d.name for d in allocated_deals])
                hard_errors_list.append(
                    f'<li><b>Already allocated:</b> {deal_names}</li>'
                )
            
            # HARD ERROR 3: Invalid states
            invalid_deals = wizard.deal_ids.filtered(lambda d: d.state not in ['confirmed', 'in_production', 'ready'])
            if invalid_deals:
                deal_names = ', '.join([f"{d.name} ({d.state})" for d in invalid_deals])
                hard_errors_list.append(
                    f'<li><b>Invalid state:</b> {deal_names}</li>'
                )
            
            # HARD ERROR 4: Missing primary subdeal
            missing_subdeal = wizard.deal_ids.filtered(lambda d: not d.primary_subdeal_id)
            if missing_subdeal:
                deal_names = ', '.join([d.name for d in missing_subdeal])
                hard_errors_list.append(
                    f'<li><b>Missing sub-deal:</b> {deal_names}</li>'
                )
            
            # SOFT WARNING 1: Mixed loading ports
            loading_ports = wizard.deal_ids.mapped('loading_port_id')
            if len(loading_ports) > 1:
                port_names = ', '.join(loading_ports.mapped('name'))
                soft_warnings_list.append(
                    f'<li><b>Mixed loading ports:</b> {port_names}</li>'
                )
            
            # SOFT WARNING 2: Mixed discharge ports
            discharge_ports = wizard.deal_ids.mapped('discharge_port_id')
            if len(discharge_ports) > 1:
                port_names = ', '.join(discharge_ports.mapped('name'))
                soft_warnings_list.append(
                    f'<li><b>Mixed discharge ports:</b> {port_names}</li>'
                )
            
            # SOFT WARNING 3: Mixed RTS dates
            rts_dates = wizard.deal_ids.filtered(lambda d: d.rts_current).mapped('rts_current')
            if len(rts_dates) > 1:
                date_range = f"{min(rts_dates)} to {max(rts_dates)}"
                soft_warnings_list.append(
                    f'<li><b>Mixed RTS dates:</b> {date_range}</li>'
                )
            
            # SOFT WARNING 4: Mixed customers (OK for consolidation)
            customers = wizard.deal_ids.mapped('customer_id')
            if len(customers) > 1:
                customer_names = ', '.join(customers.mapped('name'))
                soft_warnings_list.append(
                    f'<li><b>Multiple customers:</b> {customer_names} (consolidation)</li>'
                )
            
            # Build HTML
            if hard_errors_list:
                wizard.has_hard_errors = True
                wizard.hard_errors = '<p><b>❌ Cannot Proceed:</b></p><ul>' + ''.join(hard_errors_list) + '</ul>'
            else:
                wizard.has_hard_errors = False
                wizard.hard_errors = ''
            
            if soft_warnings_list:
                wizard.has_soft_warnings = True
                wizard.soft_warnings = '<p><b>⚠️ Warnings (can proceed):</b></p><ul>' + ''.join(soft_warnings_list) + '</ul>'
            else:
                wizard.has_soft_warnings = False
                wizard.soft_warnings = ''
    
    @api.depends('deal_ids', 'deal_ids.loading_port_id', 'deal_ids.discharge_port_id')
    def _compute_route_consistency(self):
        """Check if all deals have same route"""
        for wizard in self:
            if not wizard.deal_ids:
                wizard.route_consistent = True
                continue
            
            loading_ports = wizard.deal_ids.mapped('loading_port_id')
            discharge_ports = wizard.deal_ids.mapped('discharge_port_id')
            
            wizard.route_consistent = len(loading_ports) <= 1 and len(discharge_ports) <= 1
    
    # =========================================================================
    # DATE COMPUTATION & ONCHANGE
    # =========================================================================
    
    @api.onchange('deal_ids', 'date_strategy', 'loading_date_manual', 'etd_manual', 
                  'eta_manual', 'delivery_manual')
    def _onchange_compute_proposed_dates(self):
        """Set proposed dates based on strategy - user can then edit"""
        if self.date_strategy == 'manual':
            self.proposed_loading = self.loading_date_manual
            self.proposed_etd = self.etd_manual
            self.proposed_eta = self.eta_manual
            self.proposed_delivery = self.delivery_manual
            return
        
        if not self.deal_ids:
            self.proposed_loading = False
            self.proposed_etd = False
            self.proposed_eta = False
            self.proposed_delivery = False
            return
        
        # Collect dates from deals
        loading_dates = [d.loading_current for d in self.deal_ids if d.loading_current]
        etd_dates = [d.etd_current for d in self.deal_ids if d.etd_current]
        eta_dates = [d.eta_current for d in self.deal_ids if d.eta_current]
        delivery_dates = [d.delivery_current for d in self.deal_ids if d.delivery_current]
        
        if self.date_strategy == 'earliest_earliest':
            # Conservative: earliest of everything
            self.proposed_loading = min(loading_dates) if loading_dates else False
            self.proposed_etd = min(etd_dates) if etd_dates else False
            self.proposed_eta = min(eta_dates) if eta_dates else False
            self.proposed_delivery = min(delivery_dates) if delivery_dates else False
        
        elif self.date_strategy == 'earliest_latest':
            # Mixed: earliest start, latest finish
            self.proposed_loading = min(loading_dates) if loading_dates else False
            self.proposed_etd = min(etd_dates) if etd_dates else False
            self.proposed_eta = max(eta_dates) if eta_dates else False
            self.proposed_delivery = max(delivery_dates) if delivery_dates else False
        
        elif self.date_strategy == 'latest_latest':
            # Aggressive: latest of everything
            self.proposed_loading = max(loading_dates) if loading_dates else False
            self.proposed_etd = max(etd_dates) if etd_dates else False
            self.proposed_eta = max(eta_dates) if eta_dates else False
            self.proposed_delivery = max(delivery_dates) if delivery_dates else False
    
    @api.depends('deal_ids')
    def _compute_date_impact_lines(self):
        """Create date impact lines for each deal"""
        for wizard in self:
            # Clear existing
            wizard.date_strategy_line_ids = [(5, 0, 0)]
            
            if not wizard.deal_ids:
                continue
            
            lines = []
            for deal in wizard.deal_ids:
                lines.append((0, 0, {
                    'deal_id': deal.id,
                    'loading_current': deal.loading_current,
                    'etd_current': deal.etd_current,
                    'eta_current': deal.eta_current,
                    'delivery_current': deal.delivery_current,
                }))
            
            wizard.date_strategy_line_ids = lines
    
    # =========================================================================
    # ACTION: CREATE SHIPMENT
    # =========================================================================
    
    def action_create_shipment(self):
        """Create shipment and allocate subdeals - store milestone dates on shipment"""
        self.ensure_one()
        
        if self.has_hard_errors:
            raise UserError(_('Cannot create shipment with blocking errors'))
        
        # Collect subdeals from selected deals
        subdeals = self.deal_ids.mapped('primary_subdeal_id')
        
        if not subdeals:
            raise UserError(_('No sub-deals found for selected deals'))
        
        # Build shipment values with milestone dates
        shipment_vals = {
            'subdeal_ids': [(6, 0, subdeals.ids)],
            # Store proposed dates on shipment (Sprint B key feature)
            'loading_current': self.proposed_loading,
            'etd_current': self.proposed_etd,
            'eta_current': self.proposed_eta,
            'delivery_current': self.proposed_delivery,
        }
        
        # Create shipment
        shipment = self.env['dm.shipment'].create(shipment_vals)
        
        _logger.info(f"Created shipment {shipment.name} with {len(subdeals)} sub-deals")
        
        # Build milestone updates for subdeals/deals
        milestone_updates = {}
        if self.proposed_loading:
            milestone_updates['loading_current'] = self.proposed_loading
        if self.proposed_etd:
            milestone_updates['etd_current'] = self.proposed_etd
        if self.proposed_eta:
            milestone_updates['eta_current'] = self.proposed_eta
        if self.proposed_delivery:
            milestone_updates['delivery_current'] = self.proposed_delivery
        
        # Update each subdeal with milestone dates and allocation status
        for subdeal in subdeals:
            deal = subdeal.deal_id
            changes = []
            
            for field, new_value in milestone_updates.items():
                old_value = subdeal[field] if hasattr(subdeal, field) and subdeal[field] else deal[field]
                if old_value != new_value:
                    field_label = field.replace('_current', '').upper()
                    changes.append(f"• {field_label}: {old_value or 'Not set'} → {new_value}")
            
            # Write milestone updates to subdeal
            subdeal_updates = {
                'shipment_allocated': True,
                'shipment_id': shipment.id,
            }
            subdeal_updates.update(milestone_updates)
            subdeal.write(subdeal_updates)
            
            # Also update deal milestones for consistency (via context to skip warnings)
            if milestone_updates:
                deal.with_context(skip_milestone_warnings=True).write(milestone_updates)
            
            # Log to deal chatter
            if changes:
                deal.message_post(
                    body=_(
                        '<b>📦 Allocated to Shipment: %s</b><br/><br/>'
                        '<b>Milestone Updates:</b><br/>%s'
                    ) % (shipment.name, '<br/>'.join(changes)),
                    subject=_('Shipment Allocation'),
                    message_type='notification'
                )
            else:
                deal.message_post(
                    body=_('<b>📦 Allocated to Shipment: %s</b>') % shipment.name,
                    subject=_('Shipment Allocation'),
                    message_type='notification'
                )
        
        # Log to shipment chatter
        summary_lines = [
            f"<b>Sub-Deals Allocated:</b> {len(subdeals)}",
            f"<b>Deals:</b> {', '.join(self.deal_ids.mapped('name'))}",
            f"<b>Date Strategy:</b> {dict(self._fields['date_strategy'].selection).get(self.date_strategy)}",
        ]
        
        if milestone_updates:
            summary_lines.append("<b>Milestones Set:</b>")
            for field, value in milestone_updates.items():
                field_label = field.replace('_current', '').upper()
                summary_lines.append(f"• {field_label}: {value}")
        
        shipment.message_post(
            body='<br/>'.join(summary_lines),
            subject=_('Shipment Created'),
            message_type='notification'
        )
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shipment: %s') % shipment.name,
            'res_model': 'dm.shipment',
            'res_id': shipment.id,
            'view_mode': 'form',
            'target': 'current'
        }


class ShipmentAllocationDateStrategyLine(models.TransientModel):
    """Date impact matrix line"""
    _name = 'shipment.allocation.date.strategy.line'
    _description = 'Date Strategy Line'
    
    wizard_id = fields.Many2one(
        'shipment.allocation.wizard',
        required=True,
        ondelete='cascade'
    )
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True
    )
    
    # Current dates (from deal)
    loading_current = fields.Date(
        string='Current Loading'
    )
    
    etd_current = fields.Date(
        string='Current ETD'
    )
    
    eta_current = fields.Date(
        string='Current ETA'
    )
    
    delivery_current = fields.Date(
        string='Current Delivery'
    )
    
    # Proposed dates (from wizard)
    loading_proposed = fields.Date(
        related='wizard_id.proposed_loading',
        string='Proposed Loading'
    )
    
    etd_proposed = fields.Date(
        related='wizard_id.proposed_etd',
        string='Proposed ETD'
    )
    
    eta_proposed = fields.Date(
        related='wizard_id.proposed_eta',
        string='Proposed ETA'
    )
    
    delivery_proposed = fields.Date(
        related='wizard_id.proposed_delivery',
        string='Proposed Delivery'
    )
    
    # Impact indicators
    loading_impact = fields.Selection([
        ('earlier', 'Earlier'),
        ('same', 'Same'),
        ('later', 'Later'),
        ('new', 'New')
    ], compute='_compute_impact', string='Loading Impact')
    
    etd_impact = fields.Selection([
        ('earlier', 'Earlier'),
        ('same', 'Same'),
        ('later', 'Later'),
        ('new', 'New')
    ], compute='_compute_impact', string='ETD Impact')
    
    eta_impact = fields.Selection([
        ('earlier', 'Earlier'),
        ('same', 'Same'),
        ('later', 'Later'),
        ('new', 'New')
    ], compute='_compute_impact', string='ETA Impact')
    
    delivery_impact = fields.Selection([
        ('earlier', 'Earlier'),
        ('same', 'Same'),
        ('later', 'Later'),
        ('new', 'New')
    ], compute='_compute_impact', string='Delivery Impact')
    
    @api.depends('loading_current', 'loading_proposed', 'etd_current', 'etd_proposed',
                 'eta_current', 'eta_proposed', 'delivery_current', 'delivery_proposed')
    def _compute_impact(self):
        """Calculate impact of proposed dates vs current"""
        for line in self:
            # Loading impact
            line.loading_impact = self._calc_impact(line.loading_current, line.loading_proposed)
            # ETD impact
            line.etd_impact = self._calc_impact(line.etd_current, line.etd_proposed)
            # ETA impact
            line.eta_impact = self._calc_impact(line.eta_current, line.eta_proposed)
            # Delivery impact
            line.delivery_impact = self._calc_impact(line.delivery_current, line.delivery_proposed)
    
    def _calc_impact(self, current, proposed):
        """Helper to calculate date impact"""
        if not current and proposed:
            return 'new'
        elif not proposed:
            return 'same'
        elif current == proposed:
            return 'same'
        elif current > proposed:
            return 'earlier'
        else:
            return 'later'