# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmVendorCapacity(models.Model):
    """
    Time-Based Vendor Production Capacity
    
    Tracks vendor production capacity over time with automatic validity.
    Each vendor can have multiple capacity records representing different
    time periods (e.g., capacity increases when new lines are installed).
    """
    _name = 'dm.vendor.capacity'
    _description = 'Vendor Production Capacity (Time-Based)'
    _order = 'vendor_id, valid_from desc'
    _rec_name = 'name'
    
    # =========================================================================
    # BASIC INFORMATION
    # =========================================================================
    
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        index=True,
        help='Vendor/supplier this capacity applies to'
    )
    
    name = fields.Char(
        string='Capacity Record',
        compute='_compute_name',
        store=True,
        help='Auto-generated display name'
    )
    
    # =========================================================================
    # TIME VALIDITY (CRITICAL FOR TIME-BASED CAPACITY)
    # =========================================================================
    
    valid_from = fields.Date(
        string='Valid From',
        required=True,
        default=fields.Date.today,
        index=True,
        help='Date when this capacity becomes effective'
    )
    
    valid_to = fields.Date(
        string='Valid To',
        index=True,
        help='Leave empty for ongoing capacity. Set date for temporary capacity changes.'
    )
    
    # =========================================================================
    # CAPACITY ENTRY
    # =========================================================================
    
    period_type = fields.Selection([
        ('month', 'Per Month'),
        # Future: ('week', 'Per Week'),
        # Future: ('quarter', 'Per Quarter'),
    ], string='Period Type',
        default='month',
        required=True,
        readonly=True,  # Monthly only for now
        help='Time period for capacity measurement'
    )
    
    entry_mode = fields.Selection([
        ('teu', 'Enter in TEU'),
        ('containers', 'Enter in Containers')
    ], string='Entry Method',
        default='containers',
        required=True,
        help='Choose how to enter capacity: directly in TEU or as number of containers'
    )
    
    # === OPTION 1: Direct TEU Entry ===
    capacity_teu = fields.Float(
        string='Capacity (TEU/Month)',
        digits=(16, 2),
        help='Total monthly capacity in Twenty-foot Equivalent Units'
    )
    
    # === OPTION 2: Container-Based Entry (User-Friendly) ===
    container_type_id = fields.Many2one(
        'dm.container.type',
        string='Container Type',
        help='Type of container for capacity calculation'
    )
    
    capacity_containers = fields.Float(
        string='Capacity (Containers/Month)',
        digits=(16, 2),
        help='Number of containers the vendor can produce per month'
    )
    
    # === AUTO-CALCULATED EFFECTIVE CAPACITY ===
    effective_capacity_teu = fields.Float(
        string='Effective Capacity (TEU/Month)',
        compute='_compute_effective_capacity_teu',
        store=True,
        digits=(16, 2),
        help='Final capacity in TEU (auto-converted from containers if needed)'
    )
    
    # =========================================================================
    # STATUS & TRACKING
    # =========================================================================
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Inactive records are ignored in capacity calculations'
    )
    
    is_current = fields.Boolean(
        string='Is Current',
        compute='_compute_is_current',
        store=True,
        help='True if this capacity is currently active (today falls within validity period)'
    )
    
    is_future = fields.Boolean(
        string='Is Future',
        compute='_compute_is_future',
        store=True,
        help='True if this capacity starts in the future'
    )
    
    is_expired = fields.Boolean(
        string='Is Expired',
        compute='_compute_is_expired',
        store=True,
        help='True if this capacity has ended'
    )
    
    notes = fields.Text(
        string='Notes',
        help='e.g., "Increased capacity due to new production line installation"'
    )
    
    # =========================================================================
    # CONSTRAINTS (ONE2MANY)
    # =========================================================================
    
    constraint_ids = fields.One2many(
        'dm.vendor.capacity.constraint',
        'vendor_capacity_id',
        string='Specific Constraints',
        help='Optional product-specific or category-specific capacity limits'
    )
    
    constraint_count = fields.Integer(
        compute='_compute_constraint_count',
        string='Constraints'
    )
    
    # =========================================================================
    # DISPLAY HELPERS
    # =========================================================================
    
    display_period = fields.Char(
        compute='_compute_display_period',
        string='Validity Period'
    )
    
    status_badge = fields.Selection([
        ('current', 'Current'),
        ('future', 'Future'),
        ('expired', 'Expired')
    ], compute='_compute_status_badge',
        string='Status'
    )
    
    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================
    
    @api.depends('vendor_id', 'valid_from', 'valid_to', 'effective_capacity_teu')
    def _compute_name(self):
        """Generate display name"""
        for record in self:
            if record.vendor_id:
                period = f"from {record.valid_from}"
                if record.valid_to:
                    period += f" to {record.valid_to}"
                else:
                    period += " onwards"
                record.name = f"{record.vendor_id.name} - {period} ({record.effective_capacity_teu:.1f} TEU/month)"
            else:
                record.name = "New Capacity Record"
    
    @api.depends('entry_mode', 'capacity_teu', 'capacity_containers',
                 'container_type_id', 'container_type_id.teu_factor')
    def _compute_effective_capacity_teu(self):
        """Calculate effective capacity in TEU"""
        for record in self:
            if record.entry_mode == 'teu':
                record.effective_capacity_teu = record.capacity_teu or 0.0
            else:  # containers
                if record.capacity_containers and record.container_type_id:
                    teu_factor = record.container_type_id.teu_factor or 1.0
                    record.effective_capacity_teu = record.capacity_containers * teu_factor
                    _logger.debug(
                        f"Capacity {record.id}: {record.capacity_containers} × {teu_factor} = "
                        f"{record.effective_capacity_teu} TEU"
                    )
                else:
                    record.effective_capacity_teu = 0.0
    
    @api.depends('valid_from', 'valid_to')
    def _compute_is_current(self):
        """Check if capacity is currently valid"""
        today = fields.Date.today()
        for record in self:
            is_valid_from = record.valid_from <= today
            is_valid_to = not record.valid_to or record.valid_to >= today
            record.is_current = is_valid_from and is_valid_to
    
    @api.depends('valid_from')
    def _compute_is_future(self):
        """Check if capacity starts in the future"""
        today = fields.Date.today()
        for record in self:
            record.is_future = record.valid_from > today
    
    @api.depends('valid_to')
    def _compute_is_expired(self):
        """Check if capacity has ended"""
        today = fields.Date.today()
        for record in self:
            record.is_expired = record.valid_to and record.valid_to < today
    
    @api.depends('valid_from', 'valid_to')
    def _compute_display_period(self):
        """Generate human-readable period"""
        for record in self:
            if record.valid_to:
                record.display_period = f"{record.valid_from} to {record.valid_to}"
            else:
                record.display_period = f"From {record.valid_from} onwards"
    
    @api.depends('is_current', 'is_future', 'is_expired')
    def _compute_status_badge(self):
        """Determine status for badge display"""
        for record in self:
            if record.is_current:
                record.status_badge = 'current'
            elif record.is_future:
                record.status_badge = 'future'
            else:
                record.status_badge = 'expired'
    
    @api.depends('constraint_ids')
    def _compute_constraint_count(self):
        """Count active constraints"""
        for record in self:
            record.constraint_count = len(record.constraint_ids.filtered('active'))
    
    # =========================================================================
    # CONSTRAINTS & VALIDATION
    # =========================================================================
    
    @api.constrains('valid_from', 'valid_to')
    def _check_date_validity(self):
        """Ensure valid_to is after valid_from"""
        for record in self:
            if record.valid_to and record.valid_from > record.valid_to:
                raise ValidationError(
                    _("Valid To date must be after Valid From date.\n"
                      "Valid From: %s\n"
                      "Valid To: %s") % (record.valid_from, record.valid_to)
                )
    
    @api.constrains('vendor_id', 'valid_from', 'valid_to', 'active')
    def _check_no_overlapping_periods(self):
        """Prevent overlapping capacity periods for the same vendor"""
        for record in self:
            if not record.active:
                continue
                
            # Find other active records for same vendor
            domain = [
                ('vendor_id', '=', record.vendor_id.id),
                ('id', '!=', record.id),
                ('active', '=', True)
            ]
            
            other_records = self.search(domain)
            
            # Check for overlaps
            for other in other_records:
                if self._periods_overlap(
                    record.valid_from, record.valid_to,
                    other.valid_from, other.valid_to
                ):
                    raise ValidationError(
                        _("Capacity period overlaps with existing record:\n\n"
                          "This record: %s\n"
                          "Conflicts with: %s\n\n"
                          "Please adjust the dates to avoid overlap.") %
                        (record.display_period, other.display_period)
                    )
    
    @api.constrains('entry_mode', 'capacity_teu', 'capacity_containers', 'container_type_id')
    def _check_capacity_entry(self):
        """Validate capacity entry based on mode"""
        for record in self:
            if record.entry_mode == 'teu':
                if not record.capacity_teu or record.capacity_teu <= 0:
                    raise ValidationError(
                        _("Please enter a positive capacity value in TEU.")
                    )
            else:  # containers
                if not record.capacity_containers or record.capacity_containers <= 0:
                    raise ValidationError(
                        _("Please enter a positive number of containers.")
                    )
                if not record.container_type_id:
                    raise ValidationError(
                        _("Please select a container type for capacity calculation.")
                    )
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _periods_overlap(self, start1, end1, start2, end2):
        """
        Check if two date periods overlap
        
        Args:
            start1, end1: First period (Date fields)
            start2, end2: Second period (Date fields)
        
        Returns:
            bool: True if periods overlap
        """
        # Handle ongoing periods (no end date = 2099-12-31)
        if not end1:
            end1 = fields.Date.from_string('2099-12-31')
        if not end2:
            end2 = fields.Date.from_string('2099-12-31')
        
        # Periods overlap if: start1 <= end2 AND start2 <= end1
        return start1 <= end2 and start2 <= end1
    
    @api.model
    def get_capacity_for_date(self, vendor_id, target_date):
        """
        Get the applicable capacity record for a specific date
        
        Args:
            vendor_id: Vendor partner ID (int)
            target_date: Date to check (Date field)
        
        Returns:
            dm.vendor.capacity record or False
        """
        capacity = self.search([
            ('vendor_id', '=', vendor_id),
            ('valid_from', '<=', target_date),
            '|',
            ('valid_to', '=', False),
            ('valid_to', '>=', target_date),
            ('active', '=', True)
        ], limit=1, order='valid_from desc')
        
        if capacity:
            _logger.debug(
                f"Found capacity for vendor {vendor_id} on {target_date}: "
                f"{capacity.effective_capacity_teu} TEU/month"
            )
        else:
            _logger.debug(f"No capacity found for vendor {vendor_id} on {target_date}")
        
        return capacity
    
    @api.model
    def get_capacity_for_month(self, vendor_id, year, month):
        """
        Get capacity for a specific month
        
        Args:
            vendor_id: Vendor partner ID (int)
            year: Year (int)
            month: Month (int 1-12)
        
        Returns:
            dm.vendor.capacity record or False
        """
        # Use first day of month
        target_date = fields.Date.from_string(f'{year}-{month:02d}-01')
        return self.get_capacity_for_date(vendor_id, target_date)
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def action_view_constraints(self):
        """Open constraints for this capacity record"""
        self.ensure_one()
        return {
            'name': _('Capacity Constraints'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.vendor.capacity.constraint',
            'view_mode': 'tree,form',
            'domain': [('vendor_capacity_id', '=', self.id)],
            'context': {'default_vendor_capacity_id': self.id},
        }
    
    def action_clone_capacity(self):
        """Clone this capacity record with new dates"""
        self.ensure_one()
        
        # Determine new valid_from (day after this one ends, or today)
        if self.valid_to:
            new_from = self.valid_to + fields.timedelta(days=1)
        else:
            new_from = fields.Date.today()
        
        new_capacity = self.copy({
            'valid_from': new_from,
            'valid_to': False,
            'notes': f"Cloned from {self.name}"
        })
        
        return {
            'name': _('New Capacity Period'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.vendor.capacity',
            'view_mode': 'form',
            'res_id': new_capacity.id,
            'target': 'current',
        }