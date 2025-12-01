# -*- coding: utf-8 -*-
"""
DM Downpayment Request Model
Milestone-based payment tracking linked to standard Odoo payments

Payment Integration:
- DP Requests are analytical/business documents
- account.payment handles financial/accounting layer
- M:1 relationship: multiple DPs can link to one Payment
- State driven by payment posting (pending → paid when payment posted)
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmDownpaymentRequest(models.Model):
    _name = 'dm.downpayment.request'
    _description = 'Downpayment Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date, id'

    # ============================================================
    # CORE FIELDS
    # ============================================================

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New')
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False, index=True)

    notes = fields.Text(
        string='Notes',
        help='Additional notes or comments'
    )

    # ============================================================
    # BUSINESS REFERENCES
    # ============================================================

    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True
    )

    subdeal_id = fields.Many2one(
        'dm.deal.subdeal',
        string='Subdeal',
        ondelete='cascade',
        index=True,
        help='Subdeal this downpayment belongs to'
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        index=True,
        tracking=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )

    # ============================================================
    # MILESTONE REFERENCES
    # ============================================================

    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Payment Term',
        help='Source payment term that generated this request'
    )
    milestone_id = fields.Many2one(
        'dm.payment.milestone',
        string='Milestone',
        ondelete='set null',
        index=True,
        help='Payment milestone triggering this request'
    )

    # ============================================================
    # ORDER REFERENCES
    # ============================================================

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        ondelete='set null',
        help='Related sale order for customer downpayments'
    )

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        ondelete='set null',
        help='Related purchase order for vendor downpayments'
    )

    # ============================================================
    # FINANCIAL FIELDS
    # ============================================================

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True
    )

    amount_requested = fields.Monetary(
        string='Amount Requested',
        required=True,
        currency_field='currency_id',
        tracking=True,
        help='Total amount due for this downpayment request'
    )

    amount_received = fields.Monetary(
        string='Amount Received',
        currency_field='currency_id',
        compute='_compute_amount_received',
        store=True,
        help='Amount received (from linked payment when allocated)'
    )

    amount_remaining = fields.Monetary(
        string='Amount Remaining',
        currency_field='currency_id',
        compute='_compute_amount_remaining',
        store=True,
        help='Remaining amount to be paid'
    )

    percentage = fields.Float(
        string='Percentage',
        digits=(5, 2),
        help='Percentage of deal/subdeal value'
    )

    due_date = fields.Date(
        string='Due Date',
        required=True,
        tracking=True,
        index=True
    )

    # ============================================================
    # PAYMENT TYPE
    # ============================================================

    payment_type = fields.Selection([
        ('inbound', 'Customer Payment'),
        ('outbound', 'Vendor Payment'),
    ], string='Payment Type', required=True, default='inbound', index=True)

    is_customer_dp = fields.Boolean(
        string='Is Customer DP',
        compute='_compute_payment_type_flags',
        store=True
    )

    is_vendor_dp = fields.Boolean(
        string='Is Vendor DP',
        compute='_compute_payment_type_flags',
        store=True
    )

    # ============================================================
    # PAYMENT LINKAGE
    # ============================================================

    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        ondelete='restrict',
        index=True,
        copy=False,
        tracking=True,
        help='Linked payment document'
    )

    payment_state = fields.Selection(
        related='payment_id.state',
        string='Payment Status',
        store=True,
        help='Status of linked payment'
    )

    payment_name = fields.Char(
        related='payment_id.name',
        string='Payment Reference',
        store=True
    )

    payment_date = fields.Date(
        related='payment_id.date',
        string='Payment Date',
        store=True
    )

    is_allocated = fields.Boolean(
        string='Allocated to Payment',
        compute='_compute_is_allocated',
        store=True,
        help='True if linked to a payment document'
    )

    # ============================================================
    # INVOICE TRACKING (for reconciliation)
    # ============================================================

    invoice_ids = fields.Many2many(
        'account.move',
        'dm_downpayment_invoice_rel',
        'downpayment_id',
        'invoice_id',
        string='Applied to Invoices',
        help='Invoices this downpayment has been applied to'
    )

    # ============================================================
    # COMPUTED METHODS
    # ============================================================

    @api.depends('payment_type')
    def _compute_payment_type_flags(self):
        for rec in self:
            rec.is_customer_dp = rec.payment_type == 'inbound'
            rec.is_vendor_dp = rec.payment_type == 'outbound'

    @api.depends('payment_id')
    def _compute_is_allocated(self):
        for rec in self:
            rec.is_allocated = bool(rec.payment_id)

    @api.depends('payment_id', 'payment_id.state', 'payment_id.amount', 'amount_requested')
    def _compute_amount_received(self):
        """
        Compute amount received from linked payment.
        When M:1 (multiple DPs → one payment), pro-rate by requested amounts.
        When not allocated, amount_received = 0.
        """
        for rec in self:
            if not rec.payment_id or rec.payment_id.state not in ('posted', 'reconciled'):
                rec.amount_received = 0.0
                continue

            payment = rec.payment_id
            all_dps = payment.dp_request_ids
            total_dp_requested = sum(all_dps.mapped('amount_requested'))

            if total_dp_requested <= 0:
                rec.amount_received = 0.0
            elif len(all_dps) == 1:
                # 1:1 - full payment amount (could be different from requested)
                rec.amount_received = payment.amount
            else:
                # M:1 - pro-rate based on requested amounts
                ratio = rec.amount_requested / total_dp_requested
                rec.amount_received = payment.amount * ratio

    @api.depends('amount_requested', 'amount_received')
    def _compute_amount_remaining(self):
        for rec in self:
            rec.amount_remaining = rec.amount_requested - rec.amount_received

    # ============================================================
    # CONSTRAINTS
    # ============================================================

    @api.constrains('amount_requested')
    def _check_amounts(self):
        for rec in self:
            if rec.amount_requested <= 0:
                raise ValidationError(_('Amount requested must be positive.'))

    @api.constrains('payment_id', 'partner_id', 'currency_id', 'payment_type')
    def _check_payment_compatibility(self):
        """Ensure DP and Payment are compatible when linked"""
        for rec in self:
            if not rec.payment_id:
                continue
            payment = rec.payment_id

            if payment.partner_id != rec.partner_id:
                raise ValidationError(_(
                    "DP Request partner (%s) must match Payment partner (%s)"
                ) % (rec.partner_id.name, payment.partner_id.name))

            if payment.currency_id != rec.currency_id:
                raise ValidationError(_(
                    "DP Request currency (%s) must match Payment currency (%s)"
                ) % (rec.currency_id.name, payment.currency_id.name))

            if payment.payment_type != rec.payment_type:
                raise ValidationError(_(
                    "DP Request type (%s) must match Payment type (%s)"
                ) % (rec.payment_type, payment.payment_type))

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)',
         'Downpayment request reference must be unique per company.'),
    ]

    # ============================================================
    # LOCKING LOGIC
    # ============================================================

    PROTECTED_FIELDS = {
        'amount_requested', 'partner_id', 'currency_id',
        'deal_id', 'subdeal_id', 'payment_type', 'milestone_id'
    }

    def write(self, vals):
        """Lock critical fields when allocated to payment"""
        for rec in self:
            if rec.is_allocated and not self.env.context.get('force_dp_write'):
                # Check for protected field modifications
                changing_protected = self.PROTECTED_FIELDS & set(vals.keys())
                if changing_protected:
                    raise UserError(_(
                        "Cannot modify %s on allocated DP Request '%s'.\n"
                        "Deallocate from payment first."
                    ) % (', '.join(changing_protected), rec.name))

                # Block manual state changes (except system-triggered)
                if 'state' in vals and not self.env.context.get('from_payment_post'):
                    raise UserError(_(
                        "Cannot manually change state of allocated DP Request '%s'.\n"
                        "State is controlled by linked payment."
                    ) % rec.name)

        return super().write(vals)

    def unlink(self):
        """Block deletion of allocated DP requests"""
        allocated = self.filtered('is_allocated')
        if allocated:
            raise UserError(_(
                "Cannot delete allocated DP Requests:\n%s\n"
                "Deallocate from payment first."
            ) % ', '.join(allocated.mapped('name')))
        return super().unlink()

    # ============================================================
    # CRUD OVERRIDES
    # ============================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                payment_type = vals.get('payment_type', 'inbound')
                if payment_type == 'inbound':
                    sequence_code = 'dm.dp.customer'
                else:
                    sequence_code = 'dm.dp.supplier'

                seq = self.env['ir.sequence'].next_by_code(sequence_code)
                if not seq:
                    # Fallback to generic
                    seq = self.env['ir.sequence'].next_by_code('dm.downpayment.request')
                vals['name'] = seq or _('New')

        return super().create(vals_list)

    # ============================================================
    # STATE ACTIONS
    # ============================================================

    def action_confirm(self):
        """Confirm DP request - ready for payment allocation"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft requests can be confirmed."))
        self.write({'state': 'pending'})
        return True

    def action_cancel(self):
        """Cancel DP request"""
        for rec in self:
            if rec.is_allocated:
                raise UserError(_(
                    "Cannot cancel allocated DP Request '%s'.\n"
                    "Deallocate from payment first."
                ) % rec.name)
            if rec.state == 'paid':
                raise UserError(_(
                    "Cannot cancel paid DP Request '%s'."
                ) % rec.name)
        self.write({'state': 'cancelled'})
        return True

    def action_reset_draft(self):
        """Reset cancelled request to draft"""
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_("Only cancelled requests can be reset to draft."))
        self.write({'state': 'draft'})
        return True

    # ============================================================
    # PAYMENT ACTIONS
    # ============================================================

    def action_deallocate(self):
        """Remove DP from payment"""
        for rec in self:
            if not rec.payment_id:
                continue

            if rec.payment_id.state != 'draft':
                raise UserError(_(
                    "Cannot deallocate from posted payment '%s'.\n"
                    "Only draft payments allow deallocation."
                ) % rec.payment_id.name)

            payment_name = rec.payment_id.name
            # Revert state if was paid
            new_state = 'pending' if rec.state == 'paid' else rec.state

            rec.with_context(force_dp_write=True).write({
                'payment_id': False,
            })
            # State update outside locking context
            if rec.state != new_state:
                rec.with_context(force_dp_write=True).write({'state': new_state})

            _logger.info(
                "DP Request %s deallocated from payment %s, state → %s",
                rec.name, payment_name, new_state
            )
        return True

    def action_view_payment(self):
        """Navigate to linked payment"""
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("No payment linked to this DP Request."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment'),
            'res_model': 'account.payment',
            'res_id': self.payment_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_deal(self):
        """Navigate to source deal"""
        self.ensure_one()
        if not self.deal_id:
            raise UserError(_("No deal linked to this DP Request."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deal'),
            'res_model': 'dm.deal',
            'res_id': self.deal_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_payment_wizard(self):
        """
        Open wizard to create payment from selected DP requests.
        Called from tree view bulk action.
        """
        if not self:
            raise UserError(_("No DP requests selected."))

        # Validation: all must be pending
        invalid_states = self.filtered(lambda r: r.state != 'pending')
        if invalid_states:
            raise UserError(_(
                "All selected DP requests must be in 'Pending' state.\n"
                "Invalid: %s"
            ) % ', '.join(invalid_states.mapped('name')))

        # Validation: not already allocated
        allocated = self.filtered('is_allocated')
        if allocated:
            raise UserError(_(
                "These DP requests are already allocated to payments:\n%s"
            ) % ', '.join(allocated.mapped('name')))

        # Validation: same partner
        partners = self.mapped('partner_id')
        if len(partners) > 1:
            raise UserError(_(
                "Cannot create single payment for multiple partners.\n"
                "Selected partners: %s"
            ) % ', '.join(partners.mapped('name')))

        # Validation: same currency
        currencies = self.mapped('currency_id')
        if len(currencies) > 1:
            raise UserError(_(
                "Cannot create single payment for multiple currencies.\n"
                "Selected currencies: %s"
            ) % ', '.join(currencies.mapped('name')))

        # Validation: same payment type
        payment_types = set(self.mapped('payment_type'))
        if len(payment_types) > 1:
            raise UserError(_(
                "Cannot mix customer and vendor DP requests in single payment."
            ))

        # Get latest due date for default payment date
        due_dates = [d for d in self.mapped('due_date') if d]
        latest_due_date = max(due_dates) if due_dates else fields.Date.today()

        # Generate memo from DP names
        memo = ', '.join(self.mapped('name'))
        if len(memo) > 200:
            memo = memo[:197] + '...'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Payment'),
            'res_model': 'dm.dp.create.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_dp_request_ids': [(6, 0, self.ids)],
                'default_partner_id': partners.id,
                'default_currency_id': currencies.id,
                'default_payment_type': list(payment_types)[0],
                'default_payment_date': latest_due_date,
                'default_memo': memo,
            },
        }

    # ============================================================
    # LEGACY METHOD - DEPRECATED
    # ============================================================

    def action_register_payment(self):
        """
        DEPRECATED: Use action_create_payment_wizard instead.
        Kept for backward compatibility - redirects to new wizard.
        """
        _logger.warning(
            "action_register_payment is deprecated. Use action_create_payment_wizard. "
            "Called for DP: %s", self.mapped('name')
        )
        return self.action_create_payment_wizard()