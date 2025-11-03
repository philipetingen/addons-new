from odoo import api, fields, models, _
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDealMilestones(models.Model):
    """Deal Milestone Management Extension
    
    Extracted from dm_deal.py v3.1 + Bi-directional Sync Logic
    
    Key Features:
    - Three-layer milestone date management (requested/current/actual)
    - Bi-directional sync between requested ↔ current
    - Requested preserves original intent (never overwritten by CASCADE)
    - Current evolves through deal lifecycle
    - All sync actions logged for audit trail
    """
    _name = 'dm.deal'
    _inherit = 'dm.deal'
    
    # ============================================================
    # MILESTONE MATRIX - THREE-LAYER DATES
    # ============================================================
    
    # Milestone 1: Order Confirmation (uses confirmation_date from parent)
    
    # Milestone 2: Production Start
    production_start_requested = fields.Date(
        string='Production Start Requested',
        tracking=True,
        help='Original requested production start date - preserves initial intent'
    )
    production_start_current = fields.Date(
        string='Production Start Current',
        tracking=True,
        help='Current planned production start date - may change via CASCADE'
    )
    production_start_actual = fields.Date(
        string='Production Start Actual',
        readonly=True,
        tracking=True,
        help='Actual production start date (set by production module)'
    )
    production_start_calculated = fields.Date(
        string='Calculated Production Start',
        compute='_compute_production_start_calculated',
        store=True,
        help='Auto-calculated: RTS - Production Cycle Time'
    )
    
    # Milestone 3: Ready to Ship (RTS)
    rts_requested = fields.Date(
        string='RTS Requested',
        help='Ready to Ship date requested by customer - original baseline',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']"
    )
    rts_current = fields.Date(
        string='RTS Current',
        help='Negotiated Ready to Ship date - working value',
        tracking=True
    )
    rts_actual = fields.Date(
        string='RTS Actual',
        help='Actual Ready to Ship date',
        readonly=True,
        tracking=True
    )
    
    # Milestone 4: Loading
    loading_requested = fields.Date(
        string='Loading Requested',
        tracking=True,
        help='Requested loading date at factory - original baseline'
    )
    loading_current = fields.Date(
        string='Loading Current',
        tracking=True,
        help='Current planned loading date - working value'
    )
    loading_actual = fields.Date(
        string='Loading Actual',
        readonly=True,
        tracking=True,
        help='Actual loading date (set by shipment module)'
    )
    
    # Milestone 5: ETD (Estimated Time of Departure)
    etd_requested = fields.Date(
        string='ETD Requested',
        tracking=True,
        help='Requested vessel departure date - original baseline'
    )
    etd_current = fields.Date(
        string='ETD Current',
        tracking=True,
        help='Current estimated departure date - working value'
    )
    etd_actual = fields.Date(
        string='ETD Actual',
        readonly=True,
        tracking=True,
        help='Actual departure date (set by shipment module)'
    )
    
    # Milestone 6: ETA (Estimated Time of Arrival)
    eta_requested = fields.Date(
        string='ETA Requested',
        help='Arrival date requested by customer - original baseline',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']"
    )
    eta_current = fields.Date(
        string='ETA Current',
        help='Current estimated arrival date - working value',
        tracking=True
    )
    eta_actual = fields.Date(
        string='ETA Actual',
        help='Actual arrival date',
        readonly=True,
        tracking=True
    )
    
    # Milestone 7: Delivery
    delivery_requested = fields.Date(
        string='Delivery Requested',
        tracking=True,
        help='Requested final delivery date to customer - original baseline'
    )
    delivery_current = fields.Date(
        string='Delivery Current',
        tracking=True,
        help='Current planned delivery date - working value'
    )
    delivery_actual = fields.Date(
        string='Delivery Actual',
        readonly=True,
        tracking=True,
        help='Actual delivery date to customer'
    )
    
    # ============================================================
    # MILESTONE DATE METHODS
    # ============================================================
    
    def get_milestone_date(self, milestone_code, prefer='best'):
        """
        Get milestone date with fallback logic.
        CRITICAL: Single source of truth for milestone dates.
        
        Args:
            milestone_code: 'order_conf', 'prod_start', 'rts', 'loading', 
                           'etd', 'eta', 'delivery'
            prefer: 'actual', 'current', 'requested', or 'best' (auto-select)
        
        Returns:
            Date or False
        """
        self.ensure_one()
        
        mapping = {
            'order_conf': (self.confirmation_date, self.confirmation_date, self.confirmation_date),
            'prod_start': (self.production_start_requested, self.production_start_current or self.production_start_calculated, self.production_start_actual),
            'rts': (self.rts_requested, self.rts_current, self.rts_actual),
            'loading': (self.loading_requested, self.loading_current, self.loading_actual),
            'etd': (self.etd_requested, self.etd_current, self.etd_actual),
            'eta': (self.eta_requested, self.eta_current, self.eta_actual),
            'delivery': (self.delivery_requested, self.delivery_current, self.delivery_actual),
        }
        
        dates = mapping.get(milestone_code)
        if not dates:
            _logger.warning(f"Unknown milestone code: {milestone_code}")
            return False
        
        requested, current, actual = dates
        
        if prefer == 'actual':
            return actual
        elif prefer == 'current':
            return current or requested
        elif prefer == 'requested':
            return requested
        else:  # 'best'
            return actual or current or requested
    
    # ============================================================
    # COMPUTED METHODS
    # ============================================================
    
    @api.depends('rts_current', 'rts_requested', 'line_ids.product_id.total_production_cycle', 'production_start_requested')
    def _compute_production_start_calculated(self):
        """
        Calculate production start date from RTS minus production cycle.
        
        Note: This is a display-only computed field. The actual population of
        production_start_current happens via onchange or explicit writes.
        """
        for deal in self:
            if deal.production_start_requested:
                deal.production_start_calculated = deal.production_start_requested
                continue
            
            rts_date = deal.rts_current or deal.rts_requested
            
            if rts_date and deal.line_ids:
                max_cycle = max(
                    (line.product_id.total_production_cycle or 21)
                    for line in deal.line_ids
                )
                deal.production_start_calculated = rts_date - timedelta(days=max_cycle)
            else:
                deal.production_start_calculated = False
    
    # ============================================================
    # BI-DIRECTIONAL MILESTONE SYNC
    # ============================================================
    
    def _sync_milestone_dates(self, vals):
        """
        Bi-directional sync logic for milestone dates.
        
        Rules:
        1. requested → current: When requested set, populate current if blank
        2. current → requested: When current set, populate requested if blank
        3. requested NEVER overwritten by CASCADE updates to current
        
        This method modifies vals dict in-place before write().
        Returns: dict of warnings to show user (if any)
        """
        MILESTONE_PAIRS = [
            ('production_start_requested', 'production_start_current'),
            ('rts_requested', 'rts_current'),
            ('loading_requested', 'loading_current'),
            ('etd_requested', 'etd_current'),
            ('eta_requested', 'eta_current'),
            ('delivery_requested', 'delivery_current'),
        ]
        
        warnings = {}
        
        for requested_field, current_field in MILESTONE_PAIRS:
            # Rule 1: requested → current (user sets requested)
            if requested_field in vals and vals[requested_field]:
                # Check if current exists and differs - warn user
                current_value = self[current_field] if self else None
                if current_value and current_value != vals[requested_field]:
                    milestone_name = requested_field.replace('_requested', '').replace('_', ' ').title()
                    warnings[requested_field] = (
                        f"{milestone_name}: You changed REQUESTED to {vals[requested_field]}, "
                        f"but CURRENT is {current_value}. Consider updating CURRENT as well."
                    )
                
                # Sync to current if current is blank
                if current_field not in vals and not self[current_field]:
                    vals[current_field] = vals[requested_field]
                    _logger.info(
                        f"Deal {self.name}: Synced {requested_field} → {current_field} "
                        f"(value: {vals[requested_field]})"
                    )
            
            # Rule 2: current → requested (system/user sets current first)
            if current_field in vals and vals[current_field]:
                # Only backfill requested if it's blank AND not being set in same write
                if requested_field not in vals and not self[requested_field]:
                    vals[requested_field] = vals[current_field]
                    _logger.info(
                        f"Deal {self.name}: Backfilled {current_field} → {requested_field} "
                        f"(value: {vals[current_field]}) [ORIGINAL BASELINE]"
                    )
        
        return warnings
    
    # ============================================================
    # ONCHANGE METHODS - REQUESTED → CURRENT
    # ============================================================
    
    @api.onchange('production_start_requested')
    def _onchange_production_start_requested(self):
        """Sync requested → current"""
        if self.production_start_requested and not self.production_start_current:
            self.production_start_current = self.production_start_requested
    
    @api.onchange('rts_requested')
    def _onchange_rts_requested(self):
        """Sync requested → current"""
        if self.rts_requested and not self.rts_current:
            self.rts_current = self.rts_requested
    
    @api.onchange('loading_requested')
    def _onchange_loading_requested(self):
        """Sync requested → current"""
        if self.loading_requested and not self.loading_current:
            self.loading_current = self.loading_requested
    
    @api.onchange('etd_requested')
    def _onchange_etd_requested(self):
        """Sync requested → current"""
        if self.etd_requested and not self.etd_current:
            self.etd_current = self.etd_requested
    
    @api.onchange('eta_requested')  
    def _onchange_eta_requested(self):
        """Sync requested → current"""
        if self.eta_requested and not self.eta_current:
            self.eta_current = self.eta_requested
    
    @api.onchange('delivery_requested')
    def _onchange_delivery_requested(self):
        """Sync requested → current"""
        if self.delivery_requested and not self.delivery_current:
            self.delivery_current = self.delivery_requested
    
    # ============================================================
    # ONCHANGE METHODS - CURRENT → REQUESTED (REVERSE)
    # ============================================================
    
    @api.onchange('production_start_current')
    def _onchange_production_start_current(self):
        """
        Backfill requested from current (if requested is blank).
        
        Special case: production_start_current may be auto-populated from
        production_start_calculated, so we need to backfill requested here.
        """
        if self.production_start_current and not self.production_start_requested:
            self.production_start_requested = self.production_start_current
            
            # Note: In form view, calculated field may populate current before
            # user sees it. This onchange ensures requested captures that value.
            _logger.debug(
                f"Deal {self.name or 'NEW'}: Auto-backfilled production_start_requested "
                f"from production_start_current ({self.production_start_current})"
            )
    
    @api.onchange('rts_current')
    def _onchange_rts_current(self):
        """Backfill requested from current (if requested is blank)"""
        if self.rts_current and not self.rts_requested:
            self.rts_requested = self.rts_current
    
    @api.onchange('loading_current')
    def _onchange_loading_current(self):
        """Backfill requested from current (if requested is blank)"""
        if self.loading_current and not self.loading_requested:
            self.loading_requested = self.loading_current
    
    @api.onchange('etd_current')
    def _onchange_etd_current(self):
        """Backfill requested from current (if requested is blank)"""
        if self.etd_current and not self.etd_requested:
            self.etd_requested = self.etd_current
    
    @api.onchange('eta_current')
    def _onchange_eta_current(self):
        """Backfill requested from current (if requested is blank)"""
        if self.eta_current and not self.eta_requested:
            self.eta_requested = self.eta_current
    
    @api.onchange('delivery_current')
    def _onchange_delivery_current(self):
        """Backfill requested from current (if requested is blank)"""
        if self.delivery_current and not self.delivery_requested:
            self.delivery_requested = self.delivery_current
    
    # ============================================================
    # CRUD OVERRIDES
    # ============================================================
    
    @api.model
    def create(self, vals):
        """Apply milestone sync logic on create (handles imports)"""
        # Create temporary recordset for sync logic
        temp_deal = self.new(vals)
        temp_deal._sync_milestone_dates(vals)
        
        return super(DmDealMilestones, self).create(vals)
    
    def write(self, vals):
        """Apply milestone sync logic on write (handles CASCADE and programmatic updates)"""
        warnings_to_show = []
        
        for deal in self:
            # Special handling: if production_start_calculated changed and current is blank,
            # auto-populate current from calculated (which will trigger sync to requested)
            if 'production_start_calculated' not in vals:  # Avoid computed field writes
                if deal.production_start_calculated and not deal.production_start_current:
                    if 'production_start_current' not in vals:
                        vals['production_start_current'] = deal.production_start_calculated
                        _logger.info(
                            f"Deal {deal.name}: Auto-populated production_start_current from "
                            f"production_start_calculated ({deal.production_start_calculated})"
                        )
            
            warnings = deal._sync_milestone_dates(vals)
            if warnings:
                warnings_to_show.extend(warnings.values())
        
        result = super(DmDealMilestones, self).write(vals)
        
        # Show warnings to user after successful write
        if warnings_to_show and not self._context.get('skip_milestone_warnings'):
            warning_text = '\n\n'.join(warnings_to_show)
            self.message_post(
                body=_('<b>⚠️ Milestone Date Mismatch</b><br/><br/>%s') % warning_text.replace('\n', '<br/>'),
                subject=_('Milestone Date Warning'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
        
        return result