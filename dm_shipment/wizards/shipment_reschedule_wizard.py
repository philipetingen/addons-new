# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class ShipmentRescheduleWizard(models.TransientModel):
    """Wizard for rescheduling shipment milestones with impact analysis"""
    _name = 'shipment.reschedule.wizard'
    _description = 'Shipment Rescheduling Wizard'
    
    # =========================================================================
    # REFERENCE
    # =========================================================================
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        required=True,
        readonly=True
    )
    
    shipment_name = fields.Char(
        related='shipment_id.name',
        string='Shipment Reference'
    )
    
    # =========================================================================
    # CASCADE MODE
    # =========================================================================
    
    cascade_mode = fields.Selection([
        ('single', 'Adjust Single Milestone'),
        ('cascade', 'Cascade Shift to Subsequent Milestones')
    ], string='Adjustment Mode',
        default='cascade',
        required=True,
        help='Single: Only change the milestone you edit\n'
             'Cascade: Shift subsequent milestones by the same number of days'
    )
    
    # =========================================================================
    # CURRENT VALUES (from shipment - readonly)
    # =========================================================================
    
    loading_current_old = fields.Date(
        string='Loading (Current)',
        readonly=True
    )
    
    etd_current_old = fields.Date(
        string='ETD (Current)',
        readonly=True
    )
    
    eta_current_old = fields.Date(
        string='ETA (Current)',
        readonly=True
    )
    
    delivery_current_old = fields.Date(
        string='Delivery (Current)',
        readonly=True
    )
    
    # =========================================================================
    # NEW VALUES (editable)
    # =========================================================================
    
    loading_current_new = fields.Date(
        string='Loading (New)'
    )
    
    etd_current_new = fields.Date(
        string='ETD (New)'
    )
    
    eta_current_new = fields.Date(
        string='ETA (New)'
    )
    
    delivery_current_new = fields.Date(
        string='Delivery (New)'
    )
    
    # =========================================================================
    # COMPUTED SHIFTS
    # =========================================================================
    
    loading_shift = fields.Integer(
        string='Loading Shift (days)',
        compute='_compute_shifts'
    )
    
    etd_shift = fields.Integer(
        string='ETD Shift (days)',
        compute='_compute_shifts'
    )
    
    eta_shift = fields.Integer(
        string='ETA Shift (days)',
        compute='_compute_shifts'
    )
    
    delivery_shift = fields.Integer(
        string='Delivery Shift (days)',
        compute='_compute_shifts'
    )
    
    # =========================================================================
    # IMPACT ANALYSIS
    # =========================================================================
    
    affected_deal_count = fields.Integer(
        string='Affected Deals',
        compute='_compute_affected_deals'
    )
    
    affected_deal_ids = fields.Many2many(
        'dm.deal',
        string='Deals to Update',
        compute='_compute_affected_deals'
    )
    
    impact_line_ids = fields.One2many(
        'shipment.reschedule.wizard.line',
        'wizard_id',
        string='Impact by Deal'
    )
    
    # =========================================================================
    # COMPUTED METHODS
    # =========================================================================
    
    @api.model
    def default_get(self, fields_list):
        """Populate from shipment"""
        res = super().default_get(fields_list)
        
        shipment_id = self.env.context.get('active_id')
        if shipment_id and self.env.context.get('active_model') == 'dm.shipment':
            shipment = self.env['dm.shipment'].browse(shipment_id)
            res.update({
                'shipment_id': shipment.id,
                'loading_current_old': shipment.loading_current,
                'etd_current_old': shipment.etd_current,
                'eta_current_old': shipment.eta_current,
                'delivery_current_old': shipment.delivery_current,
                # Initialize new values with current
                'loading_current_new': shipment.loading_current,
                'etd_current_new': shipment.etd_current,
                'eta_current_new': shipment.eta_current,
                'delivery_current_new': shipment.delivery_current,
            })
            
            # Create impact lines for each deal
            impact_lines = []
            for deal in shipment.deal_ids:
                impact_lines.append((0, 0, {
                    'deal_id': deal.id,
                    'loading_current': deal.loading_current,
                    'etd_current': deal.etd_current,
                    'eta_current': deal.eta_current,
                    'delivery_current': deal.delivery_current,
                }))
            res['impact_line_ids'] = impact_lines
        
        return res
    
    @api.depends('loading_current_old', 'loading_current_new',
                 'etd_current_old', 'etd_current_new',
                 'eta_current_old', 'eta_current_new',
                 'delivery_current_old', 'delivery_current_new')
    def _compute_shifts(self):
        """Calculate day shifts for each milestone"""
        for wizard in self:
            wizard.loading_shift = self._calc_shift(
                wizard.loading_current_old, wizard.loading_current_new)
            wizard.etd_shift = self._calc_shift(
                wizard.etd_current_old, wizard.etd_current_new)
            wizard.eta_shift = self._calc_shift(
                wizard.eta_current_old, wizard.eta_current_new)
            wizard.delivery_shift = self._calc_shift(
                wizard.delivery_current_old, wizard.delivery_current_new)
    
    def _calc_shift(self, old_date, new_date):
        """Calculate days between two dates"""
        if old_date and new_date:
            return (new_date - old_date).days
        elif new_date and not old_date:
            return 0  # New date set where none existed
        return 0
    
    @api.depends('shipment_id')
    def _compute_affected_deals(self):
        """Get deals that will be affected"""
        for wizard in self:
            if wizard.shipment_id:
                deals = wizard.shipment_id.deal_ids
                wizard.affected_deal_ids = deals
                wizard.affected_deal_count = len(deals)
            else:
                wizard.affected_deal_ids = False
                wizard.affected_deal_count = 0
    
    @api.depends('shipment_id', 'loading_current_new', 'etd_current_new',
                 'eta_current_new', 'delivery_current_new')
    def _compute_impact_lines(self):
        """Create impact analysis lines for each deal"""
        for wizard in self:
            lines = []
            
            if wizard.shipment_id:
                for deal in wizard.shipment_id.deal_ids:
                    lines.append((0, 0, {
                        'deal_id': deal.id,
                        'loading_current': deal.loading_current,
                        'etd_current': deal.etd_current,
                        'eta_current': deal.eta_current,
                        'delivery_current': deal.delivery_current,
                    }))
            
            wizard.impact_line_ids = lines
    
    # =========================================================================
    # ONCHANGE FOR CASCADE MODE
    # =========================================================================
    
    @api.onchange('loading_current_new')
    def _onchange_loading_cascade(self):
        """Cascade loading date shift to subsequent milestones"""
        if self.cascade_mode != 'cascade':
            return
        
        shift = self._calc_shift(self.loading_current_old, self.loading_current_new)
        if shift and self.etd_current_old:
            self.etd_current_new = self.etd_current_old + timedelta(days=shift)
        if shift and self.eta_current_old:
            self.eta_current_new = self.eta_current_old + timedelta(days=shift)
        if shift and self.delivery_current_old:
            self.delivery_current_new = self.delivery_current_old + timedelta(days=shift)
    
    @api.onchange('etd_current_new')
    def _onchange_etd_cascade(self):
        """Cascade ETD shift to subsequent milestones"""
        if self.cascade_mode != 'cascade':
            return
        
        shift = self._calc_shift(self.etd_current_old, self.etd_current_new)
        if shift and self.eta_current_old:
            self.eta_current_new = self.eta_current_old + timedelta(days=shift)
        if shift and self.delivery_current_old:
            self.delivery_current_new = self.delivery_current_old + timedelta(days=shift)
    
    @api.onchange('eta_current_new')
    def _onchange_eta_cascade(self):
        """Cascade ETA shift to delivery"""
        if self.cascade_mode != 'cascade':
            return
        
        shift = self._calc_shift(self.eta_current_old, self.eta_current_new)
        if shift and self.delivery_current_old:
            self.delivery_current_new = self.delivery_current_old + timedelta(days=shift)
    
    # =========================================================================
    # ACTION
    # =========================================================================
    
    def action_apply_changes(self):
        """Apply rescheduling to shipment (cascades to deals automatically)"""
        self.ensure_one()
        
        # Build update dict
        update_vals = {}
        changes_log = []
        
        if self.loading_current_new != self.loading_current_old:
            update_vals['loading_current'] = self.loading_current_new
            changes_log.append(
                f"• LOADING: {self.loading_current_old or 'Not set'} → {self.loading_current_new}"
            )
        
        if self.etd_current_new != self.etd_current_old:
            update_vals['etd_current'] = self.etd_current_new
            changes_log.append(
                f"• ETD: {self.etd_current_old or 'Not set'} → {self.etd_current_new}"
            )
        
        if self.eta_current_new != self.eta_current_old:
            update_vals['eta_current'] = self.eta_current_new
            changes_log.append(
                f"• ETA: {self.eta_current_old or 'Not set'} → {self.eta_current_new}"
            )
        
        if self.delivery_current_new != self.delivery_current_old:
            update_vals['delivery_current'] = self.delivery_current_new
            changes_log.append(
                f"• DELIVERY: {self.delivery_current_old or 'Not set'} → {self.delivery_current_new}"
            )
        
        if not update_vals:
            raise UserError(_('No changes to apply'))
        
        # Write to shipment (cascade happens in shipment.write())
        self.shipment_id.write(update_vals)
        
        # Log to shipment chatter
        self.shipment_id.message_post(
            body=_(
                '<b>📅 Shipment Rescheduled</b><br/><br/>'
                '<b>Changes:</b><br/>%s<br/><br/>'
                '<b>Affected Deals:</b> %d<br/>'
                '<b>Mode:</b> %s'
            ) % (
                '<br/>'.join(changes_log),
                self.affected_deal_count,
                'Cascade' if self.cascade_mode == 'cascade' else 'Single'
            ),
            subject=_('Shipment Rescheduled'),
            message_type='notification'
        )
        
        _logger.info(
            f"Shipment {self.shipment_id.name} rescheduled: {list(update_vals.keys())}"
        )
        
        return {'type': 'ir.actions.act_window_close'}


class ShipmentRescheduleWizardLine(models.TransientModel):
    """Impact analysis line for rescheduling wizard"""
    _name = 'shipment.reschedule.wizard.line'
    _description = 'Rescheduling Impact Line'
    
    wizard_id = fields.Many2one(
        'shipment.reschedule.wizard',
        required=True,
        ondelete='cascade'
    )
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True
    )
    
    deal_name = fields.Char(
        related='deal_id.name',
        string='Deal Reference'
    )
    
    customer_id = fields.Many2one(
        related='deal_id.customer_id',
        string='Customer'
    )
    
    # Current dates (from deal)
    loading_current = fields.Date(string='Current Loading')
    etd_current = fields.Date(string='Current ETD')
    eta_current = fields.Date(string='Current ETA')
    delivery_current = fields.Date(string='Current Delivery')
    
    # New dates (from wizard)
    loading_new = fields.Date(
        related='wizard_id.loading_current_new',
        string='New Loading'
    )
    etd_new = fields.Date(
        related='wizard_id.etd_current_new',
        string='New ETD'
    )
    eta_new = fields.Date(
        related='wizard_id.eta_current_new',
        string='New ETA'
    )
    delivery_new = fields.Date(
        related='wizard_id.delivery_current_new',
        string='New Delivery'
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
    
    @api.depends('loading_current', 'loading_new', 'etd_current', 'etd_new',
                 'eta_current', 'eta_new', 'delivery_current', 'delivery_new')
    def _compute_impact(self):
        """Calculate impact of new dates vs current"""
        for line in self:
            line.loading_impact = self._calc_impact(line.loading_current, line.loading_new)
            line.etd_impact = self._calc_impact(line.etd_current, line.etd_new)
            line.eta_impact = self._calc_impact(line.eta_current, line.eta_new)
            line.delivery_impact = self._calc_impact(line.delivery_current, line.delivery_new)
    
    def _calc_impact(self, current, new):
        """Helper to calculate date impact"""
        if not current and new:
            return 'new'
        elif not new:
            return 'same'
        elif current == new:
            return 'same'
        elif current > new:
            return 'earlier'
        else:
            return 'later'