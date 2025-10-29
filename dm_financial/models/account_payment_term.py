from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentTerm(models.Model):
    """
    Extend payment terms with CAD compliance and milestone features.
    Integrates with DonnaMello operational milestones for accurate payment scheduling.
    """
    _inherit = 'account.payment.term'
    
    # CAD Compliance
    is_cad_compliant = fields.Boolean(
        string='CAD Compliant',
        default=False,
        tracking=True,
        help='Cash Against Documents compliant payment term'
    )
    
    cad_term_type = fields.Selection([
        ('custom', 'Custom Terms'),
        ('net', 'Net Terms'),
        ('cod', 'Cash on Delivery'),
        ('cia', 'Cash in Advance'),
        ('lc', 'Letter of Credit'),
        ('dp_balance', 'Downpayment + Balance'),
    ], string='CAD Term Type', default='custom', tracking=True)
    
    max_payment_days = fields.Integer(
        string='Max Payment Days',
        default=30,
        help='Maximum days for payment (CAD compliance max: 120)'
    )
    
    # Milestone Features
    use_milestone_payments = fields.Boolean(
        string='Use Milestone Payments',
        default=False,
        tracking=True,
        help='Enable milestone-based payment scheduling instead of fixed days'
    )
    
    requires_downpayment = fields.Boolean(
        string='Requires Downpayment',
        compute='_compute_requires_downpayment',
        store=True,
        help='Has downpayment lines (typically 15-25%)'
    )
    
    downpayment_percentage = fields.Float(
        string='Downpayment %',
        compute='_compute_downpayment_percentage',
        store=True,
        help='Total downpayment percentage'
    )
    
    payment_structure_display = fields.Char(
        string='Payment Structure',
        compute='_compute_payment_structure_display',
        help='Human-readable payment structure'
    )
    
    # Context-specific usage
    usage_context = fields.Selection([
        ('both', 'Both Sales and Purchase'),
        ('sales', 'Sales Only'),
        ('purchase', 'Purchase Only'),
    ], string='Usage Context', default='both',
       help='Where this payment term can be used')
    
    compliance_notes = fields.Text(
        string='Compliance Notes',
        help='Notes about CAD compliance requirements'
    )
    
    # Common milestone configurations
    standard_configuration = fields.Selection([
        ('20_80_order_eta', '20% Order Conf, 80% Before ETA'),
        ('25_75_rts_eta', '25% Before RTS, 75% Before ETA'),
        ('30_70_order_delivery', '30% Order, 70% Delivery'),
        ('100_eta', '100% Before ETA'),
        ('custom', 'Custom Configuration'),
    ], string='Standard Configuration', default='custom')
    
    @api.depends('line_ids.is_downpayment')
    def _compute_requires_downpayment(self):
        """Check if any line is marked as downpayment"""
        for term in self:
            term.requires_downpayment = any(line.is_downpayment for line in term.line_ids)
    
    @api.depends('line_ids.is_downpayment', 'line_ids.value', 'line_ids.value_amount')
    def _compute_downpayment_percentage(self):
        """Calculate total downpayment percentage (typically 15-25%)"""
        for term in self:
            dp_percentage = 0
            for line in term.line_ids.filtered('is_downpayment'):
                if line.value == 'percent':
                    dp_percentage += line.value_amount
            term.downpayment_percentage = dp_percentage
    
    @api.depends('line_ids', 'use_milestone_payments')
    def _compute_payment_structure_display(self):
        """Generate human-readable payment structure"""
        for term in self:
            if not term.line_ids:
                term.payment_structure_display = 'No payment lines'
                continue
            
            parts = []
            for line in term.line_ids.sorted('sequence'):
                # Amount part
                if line.value == 'percent':
                    amount_str = f"{line.value_amount}%"
                elif line.value == 'fixed':
                    amount_str = f"Fixed {line.value_amount}"
                else:
                    amount_str = "Balance"
                
                # Timing part
                if term.use_milestone_payments and line.milestone_type_id:
                    if line.milestone_timing == 'before':
                        timing_str = f"{line.milestone_days}d before {line.milestone_type_id.name}"
                    elif line.milestone_timing == 'after':
                        timing_str = f"{line.milestone_days}d after {line.milestone_type_id.name}"
                    else:
                        timing_str = f"on {line.milestone_type_id.name}"
                    parts.append(f"{amount_str} @ {timing_str}")
                else:
                    if line.nb_days:
                        parts.append(f"{amount_str} @ {line.nb_days} days")
                    else:
                        parts.append(amount_str)
            
            term.payment_structure_display = ' + '.join(parts)
    
    @api.constrains('max_payment_days', 'is_cad_compliant')
    def _check_max_payment_days(self):
        """Validate max payment days for CAD compliance (120 days max)"""
        for term in self:
            if term.is_cad_compliant and term.max_payment_days > 120:
                raise ValidationError(
                    "CAD compliant payment terms cannot exceed 120 days"
                )
    
    @api.constrains('line_ids')
    def _check_payment_lines(self):
        """Validate payment percentages don't exceed 100%"""
        for term in self:
            total_percentage = sum(
                line.value_amount 
                for line in term.line_ids 
                if line.value == 'percent'
            )
            if total_percentage > 100:
                raise ValidationError(
                    f"Total payment percentages ({total_percentage}%) exceed 100%"
                )
            
            # Check downpayment percentage is reasonable (15-25% typical)
            if term.downpayment_percentage > 0:
                if term.downpayment_percentage < 10:
                    _logger.warning(f"Low downpayment percentage: {term.downpayment_percentage}%")
                elif term.downpayment_percentage > 50:
                    _logger.warning(f"High downpayment percentage: {term.downpayment_percentage}%")
    
    @api.onchange('standard_configuration')
    def _onchange_standard_configuration(self):
        """Apply standard payment configurations"""
        if self.standard_configuration and self.standard_configuration != 'custom':
            # Clear existing lines
            self.line_ids = [(5, 0, 0)]
            
            # Get milestone type references from master data
            MilestoneType = self.env['dm.milestone.type']
            order_conf = MilestoneType.search([('milestone_code', '=', 'order_conf')], limit=1)
            rts = MilestoneType.search([('milestone_code', '=', 'rts')], limit=1)
            eta = MilestoneType.search([('milestone_code', '=', 'eta')], limit=1)
            delivery = MilestoneType.search([('milestone_code', '=', 'delivery')], limit=1)
            
            lines = []
            
            if self.standard_configuration == '20_80_order_eta':
                # 20% at order confirmation
                if order_conf:
                    lines.append((0, 0, {
                        'sequence': 10,
                        'value': 'percent',
                        'value_amount': 20.0,
                        'milestone_mode': 'milestone',
                        'milestone_type_id': order_conf.id,
                        'milestone_timing': 'on',
                        'milestone_days': 0,
                        'is_downpayment': True,
                    }))
                # 80% 7 days before ETA
                if eta:
                    lines.append((0, 0, {
                        'sequence': 20,
                        'value': 'percent',
                        'value_amount': 80.0,
                        'milestone_mode': 'milestone',
                        'milestone_type_id': eta.id,
                        'milestone_timing': 'before',
                        'milestone_days': 7,
                        'requires_bol_release': True,
                    }))
                
            elif self.standard_configuration == '25_75_rts_eta':
                # 25% 14 days before RTS
                if rts:
                    lines.append((0, 0, {
                        'sequence': 10,
                        'value': 'percent',
                        'value_amount': 25.0,
                        'milestone_mode': 'milestone',
                        'milestone_type_id': rts.id,
                        'milestone_timing': 'before',
                        'milestone_days': 14,
                        'is_downpayment': True,
                    }))
                # 75% 3 days before ETA
                if eta:
                    lines.append((0, 0, {
                        'sequence': 20,
                        'value': 'percent',
                        'value_amount': 75.0,
                        'milestone_mode': 'milestone',
                        'milestone_type_id': eta.id,
                        'milestone_timing': 'before',
                        'milestone_days': 3,
                        'requires_bol_release': True,
                    }))
                
            elif self.standard_configuration == '30_70_order_delivery':
                # 30% at order
                if order_conf:
                    lines.append((0, 0, {
                        'sequence': 10,
                        'value': 'percent',
                        'value_amount': 30.0,
                        'milestone_mode': 'milestone',
                        'milestone_type_id': order_conf.id,
                        'milestone_timing': 'on',
                        'milestone_days': 0,
                        'is_downpayment': True,
                    }))
                # 70% at delivery
                if delivery:
                    lines.append((0, 0, {
                        'sequence': 20,
                        'value': 'percent',
                        'value_amount': 70.0,
                        'milestone_mode': 'milestone',
                        'milestone_type_id': delivery.id,
                        'milestone_timing': 'on',
                        'milestone_days': 0,
                    }))
                
            elif self.standard_configuration == '100_eta':
                # 100% before ETA
                if eta:
                    lines.append((0, 0, {
                        'sequence': 10,
                        'value': 'percent',
                        'value_amount': 100.0,
                        'milestone_mode': 'milestone',
                        'milestone_type_id': eta.id,
                        'milestone_timing': 'before',
                        'milestone_days': 7,
                        'requires_bol_release': True,
                    }))
            
            self.line_ids = lines
            self.use_milestone_payments = True
            self.is_cad_compliant = True
    
    def compute_with_milestones(self, reference_dates, total_amount, context=None):
        """
        Compute payment schedule based on milestones and actual operational dates.
        
        Args:
            reference_dates: Dict of available dates from deal
            total_amount: Total amount to be paid
            context: Additional context (e.g., {'type': 'sales'} or {'type': 'purchase'})
            
        Returns:
            List of tuples (date, amount, line_reference)
        """
        self.ensure_one()
        
        if not self.use_milestone_payments:
            # Fall back to standard computation
            return super().compute(total_amount, date_ref=reference_dates.get('invoice_date', fields.Date.today()))
        
        schedule = []
        remaining_amount = total_amount
        
        for line in self.line_ids.sorted('sequence'):
            # Check context
            if context and 'type' in context:
                if line.payment_context != 'both':
                    if context['type'] == 'sales' and line.payment_context != 'sales':
                        continue
                    if context['type'] == 'purchase' and line.payment_context != 'purchase':
                        continue
            
            # Calculate amount
            if line.value == 'percent':
                amount = total_amount * (line.value_amount / 100.0)
            elif line.value == 'fixed':
                amount = min(line.value_amount, remaining_amount)
            else:  # balance
                amount = remaining_amount
            
            if amount <= 0:
                continue
            
            # Calculate date
            payment_date = None
            
            if line.milestone_mode == 'milestone' and line.milestone_type_id:
                # Get milestone date from deal using type's mapping
                milestone_date = line.milestone_type_id.get_milestone_date_from_reference(reference_dates)
                
                if milestone_date:
                    # Apply timing offset
                    if line.milestone_timing == 'before':
                        offset_days = -abs(line.milestone_days)
                    elif line.milestone_timing == 'after':
                        offset_days = abs(line.milestone_days)
                    else:  # 'on'
                        offset_days = 0
                    
                    payment_date = milestone_date + timedelta(days=offset_days)
                else:
                    # Fallback handling
                    if line.fallback_mode == 'immediate':
                        payment_date = fields.Date.today()
                    elif line.fallback_mode == 'skip':
                        continue
                    else:  # remaining_days or default
                        # Use typical days from order
                        days_offset = line.milestone_type_id.typical_days_from_order or 30
                        base_date = reference_dates.get('order_date', fields.Date.today())
                        payment_date = base_date + timedelta(days=days_offset)
            else:
                # Standard days-based calculation
                base_date = reference_dates.get('invoice_date', fields.Date.today())
                payment_date = base_date + timedelta(days=line.nb_days or 0)
            
            if payment_date:
                schedule.append((payment_date, amount, line))
                remaining_amount -= amount
        
        return schedule
    
    @api.model
    def create_standard_payment_terms(self):
        """Create standard DonnaMello payment terms"""
        terms_data = [
            {
                'name': 'Sales: 20% DP, 80% 7d before ETA',
                'is_cad_compliant': True,
                'cad_term_type': 'dp_balance',
                'use_milestone_payments': True,
                'usage_context': 'sales',
                'standard_configuration': '20_80_order_eta',
                'max_payment_days': 60,
            },
            {
                'name': 'Purchase: 20% DP, 80% 3d before ETA',
                'is_cad_compliant': True,
                'cad_term_type': 'dp_balance',
                'use_milestone_payments': True,
                'usage_context': 'purchase',
                'standard_configuration': '25_75_rts_eta',
                'max_payment_days': 60,
            },
            {
                'name': '100% Before ETA',
                'is_cad_compliant': True,
                'cad_term_type': 'cod',
                'use_milestone_payments': True,
                'usage_context': 'both',
                'standard_configuration': '100_eta',
                'max_payment_days': 60,
            },
        ]
        
        for term_data in terms_data:
            existing = self.search([('name', '=', term_data['name'])], limit=1)
            if not existing:
                term = self.create(term_data)
                # Apply standard configuration
                term._onchange_standard_configuration()
    
    def get_payment_schedule_for_deal(self, deal):
        """
        Generate payment schedule for a specific deal.
        
        Returns:
            List of dicts with payment information
        """
        self.ensure_one()
        
        # Gather reference dates from deal
        reference_dates = {
            'invoice_date': fields.Date.today(),
            'order_date': deal.confirmation_date or fields.Date.today(),
            'order_conf': deal.confirmation_date,
            'rts_actual': getattr(deal, 'rts_actual', None),
            'rts_current': getattr(deal, 'rts_current', None),
            'rts_planned': getattr(deal, 'rts_planned', None),
            'eta_actual': getattr(deal, 'eta_actual', None),
            'eta_current': getattr(deal, 'eta_current', None),
            'eta_planned': getattr(deal, 'eta_planned', None),
            'etd_actual': getattr(deal, 'etd_actual', None),
            'etd_current': getattr(deal, 'etd_current', None),
            'production_start_current': getattr(deal, 'production_start_current', None),
            'loading_date_current': getattr(deal, 'loading_date_current', None),
            'delivery_date': getattr(deal, 'delivery_date', None),
        }
        
        # Determine context
        context = {'type': 'sales'} if self.usage_context in ['sales', 'both'] else {'type': 'purchase'}
        
        # Get total amount
        if context['type'] == 'sales':
            total_amount = getattr(deal, 'total_value', 0) or getattr(deal, 'total_sale_amount', 0)
        else:
            total_amount = getattr(deal, 'purchase_total', 0) or getattr(deal, 'total_purchase_amount', 0)
        
        # Compute schedule
        schedule_tuples = self.compute_with_milestones(
            reference_dates,
            total_amount,
            context
        )
        
        # Format as list of dicts
        schedule = []
        for date, amount, line in schedule_tuples:
            schedule.append({
                'date': date,
                'amount': amount,
                'percentage': line.value_amount if line.value == 'percent' else None,
                'milestone': line.milestone_type_id.name if line.milestone_type_id else 'Standard',
                'is_downpayment': line.is_downpayment,
                'requires_bol': line.requires_bol_release,
                'line_id': line.id,
            })
        
        return schedule


class AccountPaymentTermLine(models.Model):
    """
    Extend payment term lines with milestone configuration.
    Supports both fixed-day and milestone-based payment scheduling.
    """
    _inherit = 'account.payment.term.line'
    _order = 'sequence, id'
    
    # Add sequence field for Odoo 17 compatibility
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order of payment line execution'
    )
    
    # Milestone Configuration - UPDATED to use dm.milestone.type
    milestone_mode = fields.Selection([
        ('standard', 'Standard Days'),
        ('milestone', 'Milestone Based'),
    ], string='Payment Mode', default='standard')
    
    milestone_type_id = fields.Many2one(
        'dm.milestone.type',
        string='Payment Milestone Type',
        help='Milestone type that triggers this payment'
    )
    
    milestone_timing = fields.Selection([
        ('before', 'Before Milestone'),
        ('after', 'After Milestone'),
        ('on', 'On Milestone'),
    ], string='Timing', default='after')
    
    milestone_days = fields.Integer(
        string='Days from Milestone',
        default=0,
        help='Days before/after milestone for payment'
    )
    
    # Downpayment Flag
    is_downpayment = fields.Boolean(
        string='Is Downpayment',
        default=False,
        help='This line represents a downpayment (typically 15-25%)'
    )
    
    # BOL Release
    requires_bol_release = fields.Boolean(
        string='Requires BOL Release',
        default=False,
        help='Payment requires Bill of Lading release'
    )
    
    # Edge Case Handling
    fallback_mode = fields.Selection([
        ('remaining_days', 'Use Remaining Days'),
        ('immediate', 'Immediate Payment'),
        ('minimum_days', 'Enforce Minimum Days'),
        ('skip', 'Skip Payment'),
    ], string='Fallback Mode', default='remaining_days',
       help='How to handle missing milestone dates')
    
    min_days_required = fields.Integer(
        string='Minimum Days Required',
        default=0,
        help='Minimum days required for payment processing'
    )
    
    payment_context = fields.Selection([
        ('both', 'Both Sales and Purchase'),
        ('sales', 'Sales Only'),
        ('purchase', 'Purchase Only'),
    ], string='Payment Context', default='both',
       help='Where this payment line applies')
    
    # Display fields
    milestone_display = fields.Char(
        string='Milestone Info',
        compute='_compute_milestone_display'
    )
    
    @api.depends('milestone_type_id', 'milestone_timing', 'milestone_days')
    def _compute_milestone_display(self):
        """Compute human-readable milestone display"""
        for line in self:
            if line.milestone_type_id:
                if line.milestone_timing == 'before':
                    line.milestone_display = f"{line.milestone_days}d before {line.milestone_type_id.name}"
                elif line.milestone_timing == 'after':
                    line.milestone_display = f"{line.milestone_days}d after {line.milestone_type_id.name}"
                else:
                    line.milestone_display = f"On {line.milestone_type_id.name}"
            else:
                line.milestone_display = f"{line.nb_days} days" if line.nb_days else "Immediate"
    
    @api.constrains('milestone_mode', 'milestone_type_id')
    def _check_milestone_configuration(self):
        """Validate milestone configuration"""
        for line in self:
            if line.milestone_mode == 'milestone' and not line.milestone_type_id:
                raise ValidationError(
                    "Milestone-based payment requires a milestone type selection"
                )
    
    @api.constrains('milestone_days', 'min_days_required')
    def _check_days(self):
        """Validate days are not negative"""
        for line in self:
            if line.milestone_days < 0 and line.milestone_timing != 'before':
                raise ValidationError("Milestone days cannot be negative unless timing is 'before'")
            if line.min_days_required < 0:
                raise ValidationError("Minimum days required cannot be negative")
    
    @api.constrains('value', 'value_amount', 'is_downpayment')
    def _check_downpayment_amount(self):
        """Validate downpayment amounts are reasonable"""
        for line in self:
            if line.is_downpayment and line.value == 'percent':
                if line.value_amount < 10:
                    _logger.warning(f"Low downpayment percentage: {line.value_amount}%")
                elif line.value_amount > 50:
                    _logger.warning(f"High downpayment percentage: {line.value_amount}%")
    
    @api.onchange('milestone_type_id')
    def _onchange_milestone_type_id(self):
        """Apply milestone defaults when selected"""
        if self.milestone_type_id:
            self.milestone_timing = self.milestone_type_id.default_timing
            self.milestone_days = self.milestone_type_id.default_days
            
            # Special handling for specific milestones
            if self.milestone_type_id.milestone_code == 'eta':
                self.requires_bol_release = True
                self.milestone_days = 7  # Default 7 days before ETA
                self.milestone_timing = 'before'
            elif self.milestone_type_id.milestone_code == 'order_conf':
                self.is_downpayment = True
                self.milestone_timing = 'on'
                self.milestone_days = 0
            elif self.milestone_type_id.milestone_code == 'rts':
                self.milestone_timing = 'before'
                self.milestone_days = 14  # Default 14 days before RTS