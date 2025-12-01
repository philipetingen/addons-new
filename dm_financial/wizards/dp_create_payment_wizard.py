# -*- coding: utf-8 -*-
"""
Wizard to create Payment from DP Requests

Usage:
- Select DP Requests in tree view
- Actions → Create Payment
- Wizard validates compatibility, creates draft payment, links DPs
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DpCreatePaymentWizard(models.TransientModel):
    _name = 'dm.dp.create.payment.wizard'
    _description = 'Create Payment from DP Requests'

    # ============================================================
    # DP REQUESTS
    # ============================================================

    dp_request_ids = fields.Many2many(
        'dm.downpayment.request',
        'dp_create_wizard_dp_rel',
        'wizard_id',
        'dp_id',
        string='DP Requests',
        required=True
    )

    dp_count = fields.Integer(
        string='DP Count',
        compute='_compute_dp_info'
    )

    dp_display = fields.Text(
        string='Selected DPs',
        compute='_compute_dp_info'
    )

    # ============================================================
    # PAYMENT INFO (from DPs - readonly)
    # ============================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        readonly=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        readonly=True
    )

    payment_type = fields.Selection([
        ('inbound', 'Receive Money'),
        ('outbound', 'Send Money'),
    ], string='Payment Type', required=True, readonly=True)

    payment_type_label = fields.Char(
        compute='_compute_payment_type_label'
    )

    total_dp_amount = fields.Monetary(
        string='Total DP Amount',
        compute='_compute_dp_info',
        currency_field='currency_id'
    )

    # ============================================================
    # PAYMENT DETAILS (user editable)
    # ============================================================

    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', company_id)]"
    )

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company
    )

    payment_date = fields.Date(
        string='Payment Date',
        required=True,
        default=fields.Date.today
    )

    amount = fields.Monetary(
        string='Payment Amount',
        required=True,
        currency_field='currency_id'
    )

    memo = fields.Char(
        string='Memo',
        help='Payment reference/memo (auto-generated from DP names, editable)'
    )

    # ============================================================
    # VALIDATION DISPLAY
    # ============================================================

    amount_difference = fields.Monetary(
        string='Difference',
        compute='_compute_amount_difference',
        currency_field='currency_id'
    )

    show_amount_warning = fields.Boolean(
        compute='_compute_amount_difference'
    )

    warning_message = fields.Char(
        compute='_compute_amount_difference'
    )

    # ============================================================
    # COMPUTED METHODS
    # ============================================================

    @api.depends('dp_request_ids')
    def _compute_dp_info(self):
        for wiz in self:
            dps = wiz.dp_request_ids
            wiz.dp_count = len(dps)
            wiz.total_dp_amount = sum(dps.mapped('amount_requested'))

            # Build display text
            if dps:
                lines = []
                for dp in dps[:10]:  # Limit display
                    lines.append(f"• {dp.name}: {dp.amount_requested:,.2f} {dp.currency_id.name}")
                if len(dps) > 10:
                    lines.append(f"  ... and {len(dps) - 10} more")
                wiz.dp_display = '\n'.join(lines)
            else:
                wiz.dp_display = 'No DP Requests selected'

    @api.depends('payment_type')
    def _compute_payment_type_label(self):
        for wiz in self:
            if wiz.payment_type == 'inbound':
                wiz.payment_type_label = _('Customer Payment (Receive)')
            else:
                wiz.payment_type_label = _('Vendor Payment (Send)')

    @api.depends('amount', 'total_dp_amount')
    def _compute_amount_difference(self):
        for wiz in self:
            diff = wiz.amount - wiz.total_dp_amount
            wiz.amount_difference = diff
            wiz.show_amount_warning = abs(diff) > 0.01

            if wiz.show_amount_warning:
                if diff > 0:
                    wiz.warning_message = _(
                        "Payment amount exceeds DP total by %s %s"
                    ) % (f"{diff:,.2f}", wiz.currency_id.name)
                else:
                    wiz.warning_message = _(
                        "Payment amount is less than DP total by %s %s"
                    ) % (f"{abs(diff):,.2f}", wiz.currency_id.name)
            else:
                wiz.warning_message = False

    # ============================================================
    # ONCHANGE
    # ============================================================

    @api.onchange('dp_request_ids')
    def _onchange_dp_request_ids(self):
        """Update amount when DPs change"""
        if self.dp_request_ids:
            self.amount = sum(self.dp_request_ids.mapped('amount_requested'))

    # ============================================================
    # DEFAULTS
    # ============================================================

    @api.model
    def default_get(self, fields_list):
        """Set default journal from company config or find 'Bank' journal"""
        res = super().default_get(fields_list)

        company = self.env.company

        # Try company config first (if field exists)
        if hasattr(company, 'dm_default_payment_journal_id') and company.dm_default_payment_journal_id:
            res['journal_id'] = company.dm_default_payment_journal_id.id
        else:
            # Fallback: find journal named 'Bank' or similar
            bank_journal = self.env['account.journal'].search([
                ('type', '=', 'bank'),
                ('company_id', '=', company.id),
            ], limit=1, order='id')

            # Try to find one with 'Bank' in name
            named_bank = self.env['account.journal'].search([
                ('type', '=', 'bank'),
                ('company_id', '=', company.id),
                '|', '|',
                ('name', 'ilike', 'Bank'),
                ('name', 'ilike', 'בנק'),
                ('code', 'ilike', 'BNK'),
            ], limit=1)

            if named_bank:
                res['journal_id'] = named_bank.id
            elif bank_journal:
                res['journal_id'] = bank_journal.id

        # Set amount from DP total if DPs provided in context
        if 'default_dp_request_ids' in self.env.context:
            dp_cmd = self.env.context['default_dp_request_ids']
            if dp_cmd and isinstance(dp_cmd, list) and dp_cmd[0][0] == 6:
                dp_ids = dp_cmd[0][2]
                dps = self.env['dm.downpayment.request'].browse(dp_ids)
                res['amount'] = sum(dps.mapped('amount_requested'))

        return res

    # ============================================================
    # ACTIONS
    # ============================================================

    def action_create_payment(self):
        """Create payment and link DP requests"""
        self.ensure_one()

        # Validations
        if not self.dp_request_ids:
            raise UserError(_("No DP requests selected."))

        if not self.journal_id:
            raise UserError(_("Please select a payment journal."))

        if self.amount <= 0:
            raise UserError(_("Payment amount must be positive."))

        # Re-validate DP states (could have changed)
        invalid = self.dp_request_ids.filtered(lambda r: r.state != 'pending')
        if invalid:
            raise UserError(_(
                "The following DP requests are no longer in 'Pending' state:\n%s"
            ) % ', '.join(invalid.mapped('name')))

        allocated = self.dp_request_ids.filtered('is_allocated')
        if allocated:
            raise UserError(_(
                "The following DP requests are now allocated to other payments:\n%s"
            ) % ', '.join(allocated.mapped('name')))

        # Create payment
        payment_vals = {
            'payment_type': self.payment_type,
            'partner_type': 'customer' if self.payment_type == 'inbound' else 'supplier',
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'ref': self.memo or False,
        }

        payment = self.env['account.payment'].create(payment_vals)

        # Link DP requests
        self.dp_request_ids.with_context(force_dp_write=True).write({
            'payment_id': payment.id
        })

        _logger.info(
            "Created payment %s (%s %s) for %d DP requests: %s",
            payment.name,
            self.amount,
            self.currency_id.name,
            len(self.dp_request_ids),
            ', '.join(self.dp_request_ids.mapped('name'))
        )

        # Log on payment chatter
        dp_list = '\n'.join([
            f"• {dp.name}: {dp.amount_requested:,.2f} {dp.currency_id.name}"
            for dp in self.dp_request_ids
        ])
        payment.message_post(
            body=_(
                "Payment created from DP Requests:\n%s\n\n"
                "Total DP Amount: %s %s"
            ) % (dp_list, f"{self.total_dp_amount:,.2f}", self.currency_id.name),
            message_type='comment'
        )

        # Return payment form
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment'),
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        """Close wizard without action"""
        return {'type': 'ir.actions.act_window_close'}