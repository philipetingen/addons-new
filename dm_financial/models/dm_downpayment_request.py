from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDownpaymentRequest(models.Model):
    """
    Manages downpayment requests for both customers and suppliers.
    Automatically created on deal confirmation with milestone-based due dates.
    Typical percentages: 15-25% of deal value.
    """
    _name = 'dm.downpayment.request'
    _description = 'Downpayment Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date, name'
    _rec_name = 'name'
    
    # Identification
    name = fields.Char(
        'Request Number',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
        index=True
    )
    
    # Type and Deal
    request_type = fields.Selection([
        ('customer', 'Customer (Receivable)'),
        ('supplier', 'Supplier (Payable)')
    ], string='Type', required=True, tracking=True, index=True)
    
    deal_id = fields.Many2one(
        'dm.deal',
        'Deal',
        required=True,
        ondelete='restrict',
        tracking=True,
        index=True
    )
    
    # Link to payment milestone if created from milestone
    milestone_id = fields.Many2one(
        'dm.payment.milestone',
        'Payment Milestone',
        ondelete='set null',
        help='Related payment milestone if created from milestone'
    )
    
    # Related fields from deal
    partner_id = fields.Many2one(
        'res.partner',
        'Partner',
        compute='_compute_partner',
        store=True,
        readonly=True,
        index=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='deal_id.currency_id',
        store=True,
        readonly=True
    )
    
    customer_po_number = fields.Char(
        related='deal_id.customer_po_number',
        string='Customer PO#',
        store=True,
        readonly=True
    )
    
    # Amounts
    deal_total = fields.Monetary(
        'Deal Total',
        compute='_compute_deal_total',
        store=True,
        currency_field='currency_id'
    )
    
    percentage = fields.Float(
        'Downpayment %',
        required=True,
        tracking=True,
        default=20.0,
        help='Percentage of deal total (typically 15-25%)'
    )
    
    amount_requested = fields.Monetary(
        'Amount Requested',
        compute='_compute_amount_requested',
        store=True,
        currency_field='currency_id',
        tracking=True
    )
    
    amount_received = fields.Monetary(
        'Amount Received',
        currency_field='currency_id',
        tracking=True,
        readonly=True,
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}
    )
    
    amount_due = fields.Monetary(
        'Amount Due',
        compute='_compute_amount_due',
        store=True,
        currency_field='currency_id'
    )
    
    # Milestone-based due date calculation
    milestone_trigger = fields.Selection([
        ('confirmed', 'Deal Confirmed'),
        ('production_start', 'Production Start'),
        ('rts', 'Ready to Ship'),
        ('loading', 'Loading'),
        ('etd', 'Departure (ETD)'),
        ('eta', 'Arrival (ETA)'),
        ('days_before_eta', 'X Days Before ETA'),
        ('days_after_eta', 'X Days After ETA'),
        ('days_before_rts', 'X Days Before RTS'),
        ('custom', 'Custom Date')
    ], string='Due Date Trigger', required=True, default='confirmed', tracking=True)
    
    milestone_days = fields.Integer(
        'Days Offset',
        default=0,
        help='Number of days before/after milestone'
    )
    
    due_date = fields.Date(
        'Due Date',
        required=True,
        tracking=True,
        compute='_compute_due_date',
        store=True,
        readonly=False
    )
    
    payment_date = fields.Date(
        'Payment Date',
        tracking=True,
        readonly=True,
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)], 'partial': [('readonly', False)]}
    )
    
    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled')
    ], string='State', default='draft', tracking=True, required=True, index=True)
    
    # Payment details
    payment_reference = fields.Char(
        'Payment Reference',
        tracking=True,
        help='Bank transfer reference or check number'
    )
    
    bank_account_id = fields.Many2one(
        'res.partner.bank',
        'Bank Account',
        compute='_compute_bank_account',
        store=True,
        readonly=False,
        help='Bank account for payment'
    )
    
    # CAD Payment Term Integration
    payment_term_id = fields.Many2one(
        'account.payment.term',
        'Payment Terms',
        compute='_compute_payment_term',
        store=True
    )
    
    payment_term_line_id = fields.Many2one(
        'account.payment.term.line',
        'Payment Term Line',
        help='Specific payment term line this DP relates to'
    )
    
    # Notes and tracking
    notes = fields.Text('Internal Notes')
    
    reminder_sent = fields.Boolean(
        'Reminder Sent',
        tracking=True
    )
    
    reminder_date = fields.Date(
        'Last Reminder Date'
    )
    
    days_overdue = fields.Integer(
        'Days Overdue',
        compute='_compute_days_overdue'
    )
    
    # Invoice application tracking
    invoice_ids = fields.Many2many(
        'account.move',
        'dm_dp_invoice_rel',
        'dp_id',
        'invoice_id',
        string='Applied to Invoices',
        help='Invoices where this downpayment is applied'
    )
    
    invoice_count = fields.Integer(
        'Invoice Count',
        compute='_compute_invoice_count'
    )
    
    # Journal entry reference (for direct accounting)
    journal_entry_id = fields.Many2one(
        'account.move',
        'Journal Entry',
        readonly=True,
        help='Direct journal entry for this downpayment'
    )

    status_category = fields.Selection([
        ('active', 'Active'),
        ('cancelled', 'Cancelled')
    ], compute='_compute_status_category', store=True, string='Status Category')

    @api.depends('state')
    def _compute_status_category(self):
        """Compute status category for grouping"""
        for request in self:
            request.status_category = 'cancelled' if request.state == 'cancelled' else 'active'
    
    @api.model
    def create(self, vals):
        """Generate sequence based on request type"""
        if vals.get('name', 'New') == 'New':
            if vals.get('request_type') == 'customer':
                vals['name'] = self.env['ir.sequence'].next_by_code('dm.dp.customer') or 'DP-C-NEW'
            else:
                vals['name'] = self.env['ir.sequence'].next_by_code('dm.dp.supplier') or 'DP-S-NEW'
        return super().create(vals)
    
    @api.depends('deal_id', 'request_type')
    def _compute_partner(self):
        """Compute partner based on request type"""
        for request in self:
            if request.deal_id:
                if request.request_type == 'customer':
                    request.partner_id = request.deal_id.customer_id
                else:
                    request.partner_id = request.deal_id.supplier_id
            else:
                request.partner_id = False
    
    @api.depends('deal_id', 'request_type')
    def _compute_deal_total(self):
        """Compute relevant deal total based on type"""
        for request in self:
            if request.deal_id:
                if request.request_type == 'customer':
                    # Check which field exists in the deal model
                    if hasattr(request.deal_id, 'total_value'):
                        request.deal_total = request.deal_id.total_value
                    elif hasattr(request.deal_id, 'total_sale_amount'):
                        request.deal_total = request.deal_id.total_sale_amount
                    else:
                        request.deal_total = 0.0
                else:
                    # For supplier
                    if hasattr(request.deal_id, 'purchase_total'):
                        request.deal_total = request.deal_id.purchase_total
                    elif hasattr(request.deal_id, 'total_purchase_amount'):
                        request.deal_total = request.deal_id.total_purchase_amount
                    else:
                        request.deal_total = 0.0
            else:
                request.deal_total = 0.0
    
    @api.depends('partner_id', 'request_type')
    def _compute_bank_account(self):
        """Get default bank account"""
        for request in self:
            if request.partner_id:
                if request.request_type == 'customer':
                    # Our bank account for receiving
                    request.bank_account_id = self.env.company.partner_id.bank_ids[:1]
                else:
                    # Supplier's bank account for paying
                    request.bank_account_id = request.partner_id.bank_ids[:1]
            else:
                request.bank_account_id = False
    
    @api.depends('deal_id', 'request_type')
    def _compute_payment_term(self):
        """Get payment term from deal based on type"""
        for request in self:
            if request.deal_id:
                if request.request_type == 'customer':
                    request.payment_term_id = request.deal_id.sale_payment_term_id
                else:
                    request.payment_term_id = request.deal_id.purchase_payment_term_id
            else:
                request.payment_term_id = False
    
    @api.depends('deal_total', 'percentage')
    def _compute_amount_requested(self):
        """Calculate requested amount from percentage"""
        for request in self:
            request.amount_requested = (request.deal_total * request.percentage) / 100.0
    
    @api.depends('amount_requested', 'amount_received')
    def _compute_amount_due(self):
        """Calculate amount still due"""
        for request in self:
            request.amount_due = max(0, request.amount_requested - request.amount_received)
    
    @api.depends('milestone_trigger', 'milestone_days', 'deal_id', 
                 'deal_id.confirmation_date', 'deal_id.production_start_current',
                 'deal_id.rts_current', 'deal_id.rts_actual',
                 'deal_id.loading_date_current', 'deal_id.etd_current', 
                 'deal_id.eta_current', 'deal_id.eta_actual')
    def _compute_due_date(self):
        """Calculate due date based on milestone and CAD terms"""
        for request in self:
            if not request.deal_id or request.milestone_trigger == 'custom':
                if not request.due_date:
                    request.due_date = fields.Date.today() + timedelta(days=30)
                continue
            
            base_date = False
            
            # Get base date from milestone with proper field checks
            if request.milestone_trigger == 'confirmed':
                if hasattr(request.deal_id, 'confirmation_date'):
                    base_date = request.deal_id.confirmation_date or fields.Date.today()
                else:
                    base_date = fields.Date.today()
            elif request.milestone_trigger == 'production_start':
                if hasattr(request.deal_id, 'production_start_current'):
                    base_date = request.deal_id.production_start_current
            elif request.milestone_trigger == 'rts':
                base_date = request.deal_id.rts_actual or request.deal_id.rts_current
            elif request.milestone_trigger == 'loading':
                if hasattr(request.deal_id, 'loading_date_current'):
                    base_date = request.deal_id.loading_date_current
            elif request.milestone_trigger == 'etd':
                if hasattr(request.deal_id, 'etd_current'):
                    base_date = request.deal_id.etd_current
            elif request.milestone_trigger == 'eta':
                base_date = request.deal_id.eta_actual or request.deal_id.eta_current
            elif request.milestone_trigger in ['days_before_eta', 'days_after_eta']:
                base_date = request.deal_id.eta_actual or request.deal_id.eta_current
            elif request.milestone_trigger == 'days_before_rts':
                base_date = request.deal_id.rts_actual or request.deal_id.rts_current
            
            if base_date:
                # Apply offset days
                if 'before' in request.milestone_trigger:
                    request.due_date = base_date - timedelta(days=abs(request.milestone_days))
                elif 'after' in request.milestone_trigger:
                    request.due_date = base_date + timedelta(days=abs(request.milestone_days))
                else:
                    request.due_date = base_date + timedelta(days=request.milestone_days)
            else:
                # Fallback to today + standard terms
                if request.request_type == 'customer':
                    request.due_date = fields.Date.today() + timedelta(days=7)
                else:
                    request.due_date = fields.Date.today() + timedelta(days=30)
    
    @api.depends('due_date', 'state')
    def _compute_days_overdue(self):
        """Calculate days overdue"""
        today = fields.Date.today()
        for request in self:
            if request.state in ['sent', 'partial'] and request.due_date and request.due_date < today:
                request.days_overdue = (today - request.due_date).days
            else:
                request.days_overdue = 0
    
    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        """Count applied invoices"""
        for request in self:
            request.invoice_count = len(request.invoice_ids)
    
    @api.constrains('percentage')
    def _check_percentage(self):
        """Validate percentage is reasonable (typically 15-25%)"""
        for request in self:
            if request.percentage < 0 or request.percentage > 100:
                raise ValidationError(_('Downpayment percentage must be between 0 and 100.'))
            
            # Warn if unusual percentage
            if request.percentage < 15:
                _logger.warning(f"Low downpayment percentage: {request.percentage}% for {request.name}")
            elif request.percentage > 25 and request.percentage < 100:
                _logger.warning(f"High downpayment percentage: {request.percentage}% for {request.name}")
    
    @api.constrains('amount_received', 'amount_requested')
    def _check_amount_received(self):
        """Validate received amount doesn't exceed requested"""
        for request in self:
            if request.amount_received > request.amount_requested * 1.1:  # Allow 10% overpayment
                raise ValidationError(_('Received amount significantly exceeds requested amount.'))
    
    # Actions
    def action_send(self):
        """Send downpayment request to partner"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft requests can be sent.'))
        
        # TODO: Send email using template
        # template = self.env.ref('dm_financial.email_template_downpayment_request', False)
        # if template:
        #     template.send_mail(self.id, force_send=True)
        
        self.write({
            'state': 'sent',
            'reminder_date': fields.Date.today()
        })
        
        # Create activity for follow-up
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('Follow up on downpayment request'),
            date_deadline=self.due_date,
            user_id=self.env.user.id
        )
        
        return True
    
    def action_register_payment(self):
        """Register payment received - creates direct journal entry"""
        self.ensure_one()
        
        if self.state not in ['sent', 'partial']:
            raise UserError(_('Payment can only be registered for sent or partially paid requests.'))
        
        # Open payment wizard
        return {
            'name': _('Register Downpayment'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.downpayment.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_downpayment_id': self.id,
                'default_amount': self.amount_due,
                'default_payment_date': fields.Date.today(),
            }
        }
    
    def action_mark_paid(self):
        """Mark as fully paid"""
        self.ensure_one()
        
        if self.amount_due > 0.01:  # Small tolerance for rounding
            raise UserError(_('Cannot mark as paid - amount still due: %s') % self.amount_due)
        
        self.write({
            'state': 'paid',
            'payment_date': self.payment_date or fields.Date.today()
        })
        
        # Close activities
        self.activity_ids.filtered(lambda a: a.activity_type_id.name == 'Todo').action_done()
        
        # Update milestone if linked
        if self.milestone_id:
            self.milestone_id.update_payment_status()
        
        return True
    
    def action_cancel(self):
        """Cancel downpayment request"""
        for request in self:
            if request.state == 'paid':
                raise UserError(_('Cannot cancel paid downpayment requests.'))
            
            if request.amount_received > 0:
                raise UserError(_('Cannot cancel - payment already received. Please refund first.'))
            
            request.state = 'cancelled'
            
            # Cancel activities
            request.activity_ids.unlink()
        
        return True
    
    def action_reset_draft(self):
        """Reset to draft"""
        for request in self:
            if request.state == 'paid':
                raise UserError(_('Cannot reset paid downpayment requests.'))
            
            if request.journal_entry_id:
                raise UserError(_('Cannot reset - journal entries exist.'))
            
            request.state = 'draft'
        
        return True
    
    def action_send_reminder(self):
        """Send payment reminder"""
        self.ensure_one()
        if self.state not in ['sent', 'partial']:
            raise UserError(_('Can only send reminders for sent or partial requests.'))
        
        # TODO: Send reminder email
        # template = self.env.ref('dm_financial.email_template_downpayment_reminder', False)
        # if template:
        #     template.send_mail(self.id, force_send=True)
        
        self.write({
            'reminder_sent': True,
            'reminder_date': fields.Date.today()
        })
        
        return True
    
    def action_view_invoices(self):
        """View related invoices"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Applied Invoices'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'create': False}
        }
    
    def apply_to_invoice(self, invoice_id, amount=None):
        """
        Apply downpayment to an invoice (pro-rata or specified amount).
        Used during invoice generation to allocate downpayments.
        """
        self.ensure_one()
        if self.state != 'paid':
            raise UserError(_('Only paid downpayments can be applied to invoices.'))
        
        invoice = self.env['account.move'].browse(invoice_id)
        if not invoice:
            raise UserError(_('Invoice not found.'))
        
        # Link this downpayment to the invoice
        self.invoice_ids = [(4, invoice_id)]
        
        # The actual amount to apply
        if amount is None:
            amount = self.amount_received
        
        # Note: Actual accounting reconciliation would happen here
        # For now, we just track the relationship
        
        invoice.message_post(
            body=_('Downpayment %s applied: %s %s') % (
                self.name,
                amount,
                self.currency_id.symbol
            )
        )
        
        return amount
    
    def create_journal_entry(self, amount_paid):
        """
        Create direct journal entry for downpayment (no invoice).
        Credits/debits partner account directly.
        """
        self.ensure_one()
        
        AccountMove = self.env['account.move']
        
        # Determine accounts
        if self.request_type == 'customer':
            # Customer payment - debit bank, credit customer
            debit_account = self.env.company.bank_journal_id.default_account_id
            credit_account = self.partner_id.property_account_receivable_id
            journal = self.env.company.bank_journal_id
        else:
            # Supplier payment - debit supplier, credit bank
            debit_account = self.partner_id.property_account_payable_id
            credit_account = self.env.company.bank_journal_id.default_account_id
            journal = self.env.company.bank_journal_id
        
        # Create journal entry
        move_vals = {
            'journal_id': journal.id,
            'date': self.payment_date or fields.Date.today(),
            'ref': f"{self.name} - {self.customer_po_number}",
            'line_ids': [
                (0, 0, {
                    'account_id': debit_account.id,
                    'debit': amount_paid,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                    'name': f"Downpayment {self.name}",
                }),
                (0, 0, {
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': amount_paid,
                    'partner_id': self.partner_id.id,
                    'name': f"Downpayment {self.name}",
                }),
            ],
        }
        
        move = AccountMove.create(move_vals)
        move.action_post()
        
        self.journal_entry_id = move
        
        return move
    
    @api.model
    def create_from_deal_confirmation(self, deal):
        """
        Called when deal is confirmed to create downpayment requests.
        Typical: 20% customer DP at order, 20% supplier DP before RTS.
        """
        requests = self.env['dm.downpayment.request']
        
        # Customer downpayment
        if deal.sale_payment_term_id and hasattr(deal.sale_payment_term_id, 'requires_downpayment'):
            if deal.sale_payment_term_id.requires_downpayment:
                # Default 20% at order confirmation
                customer_dp = self.create({
                    'request_type': 'customer',
                    'deal_id': deal.id,
                    'percentage': deal.sale_payment_term_id.downpayment_percentage or 20.0,
                    'milestone_trigger': 'confirmed',
                    'milestone_days': 0,
                })
                requests |= customer_dp
                
                _logger.info(f"Created customer DP request {customer_dp.name} for deal {deal.name}")
        
        # Supplier downpayment
        if deal.purchase_payment_term_id and hasattr(deal.purchase_payment_term_id, 'requires_downpayment'):
            if deal.purchase_payment_term_id.requires_downpayment:
                # Default 20% 14 days before RTS
                supplier_dp = self.create({
                    'request_type': 'supplier',
                    'deal_id': deal.id,
                    'percentage': deal.purchase_payment_term_id.downpayment_percentage or 20.0,
                    'milestone_trigger': 'days_before_rts',
                    'milestone_days': 14,
                })
                requests |= supplier_dp
                
                _logger.info(f"Created supplier DP request {supplier_dp.name} for deal {deal.name}")
        
        return requests
    
    @api.model
    def check_overdue_requests(self):
        """Cron job to check and update overdue requests"""
        overdue = self.search([
            ('state', 'in', ['sent', 'partial']),
            ('due_date', '<', fields.Date.today())
        ])
        
        for request in overdue:
            if request.state != 'overdue':
                request.state = 'overdue'
                
                # Create high priority activity
                request.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_('OVERDUE: Downpayment %s days overdue') % request.days_overdue,
                    date_deadline=fields.Date.today(),
                    user_id=request.create_uid.id
                )
        
        return True