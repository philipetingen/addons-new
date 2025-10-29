from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class DmCashFlowProjectionWizard(models.TransientModel):
    """
    Wizard for generating or regenerating cash flow projections.
    Can be run for single deal or multiple deals.
    """
    _name = 'dm.cash.flow.projection.wizard'
    _description = 'Cash Flow Projection Wizard'
    
    # Scope
    projection_type = fields.Selection([
        ('single', 'Single Deal'),
        ('multiple', 'Multiple Deals'),
        ('all', 'All Active Deals'),
        ('date_range', 'Deals in Date Range'),
    ], string='Projection Type', default='single', required=True)
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        help='Select deal for single projection'
    )
    
    deal_ids = fields.Many2many(
        'dm.deal',
        string='Deals',
        help='Select multiple deals for projection'
    )
    
    # Date range filters
    date_from = fields.Date(
        string='From Date',
        default=fields.Date.today
    )
    
    date_to = fields.Date(
        string='To Date',
        default=lambda self: fields.Date.today() + relativedelta(months=6)
    )
    
    # Deal filters for date range type
    filter_by_rts = fields.Boolean(
        string='Filter by RTS Date',
        help='Include deals with RTS in date range'
    )
    
    filter_by_eta = fields.Boolean(
        string='Filter by ETA Date',
        help='Include deals with ETA in date range'
    )
    
    filter_by_confirmation = fields.Boolean(
        string='Filter by Confirmation Date',
        default=True,
        help='Include deals confirmed in date range'
    )
    
    # Options
    clear_existing = fields.Boolean(
        string='Clear Existing Projections',
        default=True,
        help='Remove existing projections before generating new ones'
    )
    
    include_downpayments = fields.Boolean(
        string='Include Downpayments',
        default=True
    )
    
    include_balance_payments = fields.Boolean(
        string='Include Balance Payments',
        default=True
    )
    
    include_freight_insurance = fields.Boolean(
        string='Include Freight & Insurance',
        default=True,
        help='Include freight and insurance payments where applicable'
    )
    
    # Projection details
    projection_method = fields.Selection([
        ('payment_terms', 'Based on Payment Terms'),
        ('historical', 'Based on Historical Patterns'),
        ('manual', 'Manual Milestones'),
    ], string='Projection Method', default='payment_terms', required=True)
    
    # Summary fields
    deal_count = fields.Integer(
        string='Number of Deals',
        compute='_compute_summary',
        store=True
    )
    
    total_inflow = fields.Float(
        string='Total Expected Inflows',
        compute='_compute_summary',
        store=True
    )
    
    total_outflow = fields.Float(
        string='Total Expected Outflows',
        compute='_compute_summary',
        store=True
    )
    
    net_cash_flow = fields.Float(
        string='Net Cash Flow',
        compute='_compute_summary',
        store=True
    )
    
    # Manual milestone configuration (for manual method)
    manual_milestone_ids = fields.One2many(
        'dm.cash.flow.projection.wizard.milestone',
        'wizard_id',
        string='Manual Milestones'
    )
    
    @api.onchange('projection_type')
    def _onchange_projection_type(self):
        """Clear selections when type changes"""
        if self.projection_type == 'single':
            self.deal_ids = False
        elif self.projection_type == 'multiple':
            self.deal_id = False
        elif self.projection_type == 'all':
            self.deal_id = False
            self.deal_ids = False
    
    @api.depends('projection_type', 'deal_id', 'deal_ids', 'date_from', 'date_to')
    def _compute_summary(self):
        """Compute projection summary"""
        for wizard in self:
            deals = wizard._get_deals()
            wizard.deal_count = len(deals)
            
            # Calculate expected cash flows
            total_in = 0
            total_out = 0
            
            for deal in deals:
                # Customer payments (inflows)
                if deal.payment_term_id:
                    total_in += deal.total_value
                
                # Supplier payments (outflows)
                if deal.payment_term_supplier_id:
                    total_out += deal.purchase_total
                
                # Freight and insurance outflows
                if wizard.include_freight_insurance and deal.invoice_split_config_id:
                    total_out += deal.invoice_split_config_id.freight_amount
                    total_out += deal.invoice_split_config_id.insurance_amount
            
            wizard.total_inflow = total_in
            wizard.total_outflow = total_out
            wizard.net_cash_flow = total_in - total_out
    
    def _get_deals(self):
        """Get deals based on projection type"""
        self.ensure_one()
        
        if self.projection_type == 'single':
            return self.deal_id
        elif self.projection_type == 'multiple':
            return self.deal_ids
        elif self.projection_type == 'all':
            return self.env['dm.deal'].search([
                ('state', 'not in', ['draft', 'cancelled'])
            ])
        else:  # date_range
            domain = [('state', 'not in', ['draft', 'cancelled'])]
            
            date_domain = []
            if self.filter_by_confirmation:
                date_domain.append([
                    ('confirmation_date', '>=', self.date_from),
                    ('confirmation_date', '<=', self.date_to)
                ])
            
            if self.filter_by_rts:
                date_domain.append([
                    '|', ('rts_current', '>=', self.date_from),
                    ('rts_current', '<=', self.date_to)
                ])
            
            if self.filter_by_eta:
                date_domain.append([
                    '|', ('eta_current', '>=', self.date_from),
                    ('eta_current', '<=', self.date_to)
                ])
            
            if date_domain:
                # Combine with OR logic
                if len(date_domain) > 1:
                    domain.append('|' * (len(date_domain) - 1))
                domain.extend(date_domain[0] if len(date_domain) == 1 else sum(date_domain, []))
            
            return self.env['dm.deal'].search(domain)
    
    def action_generate_projection(self):
        """Generate cash flow projections"""
        self.ensure_one()
        
        deals = self._get_deals()
        if not deals:
            raise UserError(_('No deals selected for projection.'))
        
        CashFlow = self.env['dm.cash_flow']
        
        # Clear existing if requested
        if self.clear_existing:
            existing = CashFlow.search([('deal_id', 'in', deals.ids)])
            existing.unlink()
            _logger.info(f"Cleared {len(existing)} existing cash flow projections")
        
        created_count = 0
        
        for deal in deals:
            if self.projection_method == 'payment_terms':
                created_count += self._generate_from_payment_terms(deal)
            elif self.projection_method == 'historical':
                created_count += self._generate_from_historical(deal)
            else:  # manual
                created_count += self._generate_from_manual(deal)
        
        # Show results
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cash Flow Projections'),
            'res_model': 'dm.cash_flow',
            'view_mode': 'tree,graph,pivot,form',
            'domain': [('deal_id', 'in', deals.ids)],
            'context': {
                'group_by': ['date:month', 'type']
            },
            'target': 'current',
        }
    
    def _generate_from_payment_terms(self, deal):
        """Generate projections based on payment terms"""
        CashFlow = self.env['dm.cash_flow']
        created = 0
        
        # Customer payments (inflows)
        if deal.payment_term_id and self.include_balance_payments:
            schedule = self._calculate_payment_schedule(
                deal, 
                deal.payment_term_id, 
                deal.total_value,
                'customer'
            )
            
            for date, amount, description in schedule:
                if self.date_from <= date <= self.date_to:
                    CashFlow.create({
                        'deal_id': deal.id,
                        'date': date,
                        'type': 'inflow',
                        'category': 'customer_payment',
                        'description': description,
                        'amount': amount,
                        'currency_id': deal.currency_id.id,
                        'status': 'projected',
                    })
                    created += 1
        
        # Downpayments (separate from balance)
        if self.include_downpayments:
            dp_requests = self.env['dm.downpayment.request'].search([
                ('deal_id', '=', deal.id)
            ])
            
            for dp in dp_requests:
                if dp.state != 'cancelled' and self.date_from <= dp.due_date <= self.date_to:
                    CashFlow.create({
                        'deal_id': deal.id,
                        'date': dp.due_date,
                        'type': 'inflow' if dp.request_type == 'customer' else 'outflow',
                        'category': 'customer_payment' if dp.request_type == 'customer' else 'supplier_payment',
                        'description': f"Downpayment {dp.name} ({dp.percentage}%)",
                        'amount': dp.amount_requested,
                        'currency_id': deal.currency_id.id,
                        'status': 'paid' if dp.state == 'paid' else 'confirmed' if dp.state == 'sent' else 'projected',
                    })
                    created += 1
        
        # Supplier payments (outflows)
        if deal.payment_term_supplier_id and self.include_balance_payments:
            schedule = self._calculate_payment_schedule(
                deal,
                deal.payment_term_supplier_id,
                deal.purchase_total,
                'supplier'
            )
            
            for date, amount, description in schedule:
                if self.date_from <= date <= self.date_to:
                    CashFlow.create({
                        'deal_id': deal.id,
                        'date': date,
                        'type': 'outflow',
                        'category': 'supplier_payment',
                        'description': description,
                        'amount': amount,
                        'currency_id': deal.currency_id.id,
                        'status': 'projected',
                    })
                    created += 1
        
        # Freight and insurance (outflows)
        if self.include_freight_insurance and deal.invoice_split_config_id:
            config = deal.invoice_split_config_id
            
            # Freight payment (typically at loading)
            if config.freight_amount > 0:
                freight_date = deal.loading_date_current or deal.etd_current or fields.Date.today()
                if self.date_from <= freight_date <= self.date_to:
                    CashFlow.create({
                        'deal_id': deal.id,
                        'date': freight_date,
                        'type': 'outflow',
                        'category': 'freight_payment',
                        'description': 'Freight Payment to Carrier',
                        'amount': config.freight_amount,
                        'currency_id': deal.currency_id.id,
                        'status': 'projected',
                    })
                    created += 1
            
            # Insurance payment (typically at departure)
            if config.insurance_amount > 0:
                insurance_date = deal.etd_current or fields.Date.today()
                if self.date_from <= insurance_date <= self.date_to:
                    CashFlow.create({
                        'deal_id': deal.id,
                        'date': insurance_date,
                        'type': 'outflow',
                        'category': 'insurance_payment',
                        'description': 'Insurance Premium',
                        'amount': config.insurance_amount,
                        'currency_id': deal.currency_id.id,
                        'status': 'projected',
                    })
                    created += 1
        
        return created
    
    def _calculate_payment_schedule(self, deal, payment_term, total_amount, context_type):
        """Calculate payment schedule based on payment terms"""
        schedule = []
        
        # Get reference dates from deal
        reference_dates = {
            'invoice_date': fields.Date.today(),
            'order_date': deal.confirmation_date or fields.Date.today(),
            'order_conf': deal.confirmation_date,
            'rts_actual': deal.rts_actual,
            'rts_current': deal.rts_current,
            'rts_planned': deal.rts_planned,
            'eta_actual': deal.eta_actual,
            'eta_current': deal.eta_current,
            'eta_planned': deal.eta_planned,
            'etd_actual': deal.etd_actual,
            'etd_current': deal.etd_current,
            'production_start': deal.production_start_current,
            'loading_date': deal.loading_date_current,
            'delivery_date': deal.delivery_date,
        }
        
        # Skip downpayment lines if not including downpayments
        for line in payment_term.line_ids:
            if line.is_downpayment and not self.include_downpayments:
                continue
            
            # Check payment context
            if line.payment_context != 'both':
                if context_type == 'customer' and line.payment_context != 'sales':
                    continue
                if context_type == 'supplier' and line.payment_context != 'purchase':
                    continue
            
            # Calculate amount
            if line.value == 'percent':
                amount = total_amount * (line.value_amount / 100.0)
            else:
                amount = line.value_amount or total_amount
            
            # Calculate date
            if line.milestone_mode == 'milestone' and line.milestone_id:
                base_date = line.milestone_id.get_date_from_reference(reference_dates)
                if base_date:
                    payment_date = line.milestone_id.calculate_payment_date(
                        base_date,
                        line.milestone_timing,
                        line.milestone_days
                    )
                else:
                    # Fallback to standard days
                    payment_date = fields.Date.today() + timedelta(days=line.days or 30)
            else:
                payment_date = fields.Date.today() + timedelta(days=line.days or 0)
            
            description = f"{context_type.capitalize()} Payment"
            if line.milestone_id:
                description += f" - {line.milestone_id.name}"
            if line.value == 'percent':
                description += f" ({line.value_amount}%)"
            
            schedule.append((payment_date, amount, description))
        
        return schedule
    
    def _generate_from_historical(self, deal):
        """Generate projections based on historical patterns"""
        # This is a simplified implementation
        # In production, you would analyze historical payment patterns
        
        CashFlow = self.env['dm.cash_flow']
        created = 0
        
        # Simple historical pattern: 25% at order, 75% at ETA
        if deal.total_value > 0:
            # First payment
            date1 = deal.confirmation_date or fields.Date.today()
            if self.date_from <= date1 <= self.date_to:
                CashFlow.create({
                    'deal_id': deal.id,
                    'date': date1,
                    'type': 'inflow',
                    'category': 'customer_payment',
                    'description': 'Historical Pattern - Initial Payment (25%)',
                    'amount': deal.total_value * 0.25,
                    'currency_id': deal.currency_id.id,
                    'status': 'projected',
                })
                created += 1
            
            # Balance payment
            date2 = deal.eta_current or deal.eta_planned or fields.Date.today() + timedelta(days=60)
            if self.date_from <= date2 <= self.date_to:
                CashFlow.create({
                    'deal_id': deal.id,
                    'date': date2,
                    'type': 'inflow',
                    'category': 'customer_payment',
                    'description': 'Historical Pattern - Balance Payment (75%)',
                    'amount': deal.total_value * 0.75,
                    'currency_id': deal.currency_id.id,
                    'status': 'projected',
                })
                created += 1
        
        return created
    
    def _generate_from_manual(self, deal):
        """Generate projections from manual milestone configuration"""
        CashFlow = self.env['dm.cash_flow']
        created = 0
        
        for milestone in self.manual_milestone_ids:
            # Calculate date based on milestone type
            if milestone.date_type == 'fixed':
                date = milestone.fixed_date
            elif milestone.date_type == 'days_from_confirmation':
                date = (deal.confirmation_date or fields.Date.today()) + timedelta(days=milestone.days_offset)
            elif milestone.date_type == 'days_from_rts':
                base = deal.rts_current or deal.rts_planned or fields.Date.today()
                date = base + timedelta(days=milestone.days_offset)
            else:  # days_from_eta
                base = deal.eta_current or deal.eta_planned or fields.Date.today()
                date = base + timedelta(days=milestone.days_offset)
            
            if self.date_from <= date <= self.date_to:
                # Calculate amount
                if milestone.amount_type == 'percentage':
                    if milestone.flow_type == 'inflow':
                        amount = deal.total_value * (milestone.percentage / 100.0)
                    else:
                        amount = deal.purchase_total * (milestone.percentage / 100.0)
                else:
                    amount = milestone.fixed_amount
                
                CashFlow.create({
                    'deal_id': deal.id,
                    'date': date,
                    'type': milestone.flow_type,
                    'category': 'customer_payment' if milestone.flow_type == 'inflow' else 'supplier_payment',
                    'description': milestone.description,
                    'amount': amount,
                    'currency_id': deal.currency_id.id,
                    'status': 'projected',
                })
                created += 1
        
        return created


class DmCashFlowProjectionWizardMilestone(models.TransientModel):
    """Manual milestone configuration for cash flow projection"""
    _name = 'dm.cash.flow.projection.wizard.milestone'
    _description = 'Cash Flow Projection Manual Milestone'
    _order = 'sequence'
    
    wizard_id = fields.Many2one(
        'dm.cash.flow.projection.wizard',
        required=True,
        ondelete='cascade'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    description = fields.Char(
        string='Description',
        required=True
    )
    
    flow_type = fields.Selection([
        ('inflow', 'Inflow'),
        ('outflow', 'Outflow')
    ], string='Type', required=True, default='inflow')
    
    date_type = fields.Selection([
        ('fixed', 'Fixed Date'),
        ('days_from_confirmation', 'Days from Confirmation'),
        ('days_from_rts', 'Days from RTS'),
        ('days_from_eta', 'Days from ETA'),
    ], string='Date Type', default='fixed', required=True)
    
    fixed_date = fields.Date(
        string='Fixed Date'
    )
    
    days_offset = fields.Integer(
        string='Days Offset',
        help='Number of days from reference date (negative for before)'
    )
    
    amount_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ], string='Amount Type', default='percentage', required=True)
    
    percentage = fields.Float(
        string='Percentage',
        help='Percentage of deal value'
    )
    
    fixed_amount = fields.Float(
        string='Fixed Amount'
    )
    
    @api.constrains('date_type', 'fixed_date', 'days_offset')
    def _check_date_configuration(self):
        """Validate date configuration"""
        for milestone in self:
            if milestone.date_type == 'fixed' and not milestone.fixed_date:
                raise ValidationError(_('Fixed date is required for fixed date type'))
            elif milestone.date_type != 'fixed' and milestone.days_offset is None:
                raise ValidationError(_('Days offset is required for relative date types'))
    
    @api.constrains('amount_type', 'percentage', 'fixed_amount')
    def _check_amount_configuration(self):
        """Validate amount configuration"""
        for milestone in self:
            if milestone.amount_type == 'percentage':
                if not (0 <= milestone.percentage <= 100):
                    raise ValidationError(_('Percentage must be between 0 and 100'))
            else:
                if milestone.fixed_amount < 0:
                    raise ValidationError(_('Fixed amount cannot be negative'))