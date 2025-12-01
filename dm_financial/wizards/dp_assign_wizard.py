# -*- coding: utf-8 -*-
"""
Wizard to assign DP Requests to existing Payment

Usage:
- Open from Payment form (draft state only)
- Shows available DPs matching partner/currency/type
- User selects DPs to assign
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DpAssignWizard(models.TransientModel):
    _name = 'dm.dp.assign.wizard'
    _description = 'Assign DP Requests to Payment'

    # ============================================================
    # PAYMENT REFERENCE
    # ============================================================

    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        required=True,
        readonly=True,
        ondelete='cascade'
    )

    payment_name = fields.Char(
        related='payment_id.name',
        string='Payment Reference'
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        readonly=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        readonly=True
    )

    payment_type = fields.Selection([
        ('inbound', 'Receive Money'),
        ('outbound', 'Send Money'),
    ], readonly=True)

    # ============================================================
    # PAYMENT AMOUNTS
    # ============================================================

    payment_amount = fields.Monetary(
        string='Payment Amount',
        related='payment_id.amount',
        currency_field='currency_id'
    )

    current_dp_total = fields.Monetary(
        string='Currently Allocated',
        related='payment_id.dp_total_amount',
        currency_field='currency_id'
    )

    current_dp_count = fields.Integer(
        string='Currently Allocated Count',
        related='payment_id.dp_request_count'
    )

    # ============================================================
    # DP SELECTION
    # ============================================================

    available_dp_ids = fields.Many2many(
        'dm.downpayment.request',
        'dp_assign_wizard_available_rel',
        'wizard_id',
        'dp_id',
        string='Available DP Requests',
        compute='_compute_available_dps'
    )

    available_count = fields.Integer(
        string='Available Count',
        compute='_compute_available_dps'
    )

    selected_dp_ids = fields.Many2many(
        'dm.downpayment.request',
        'dp_assign_wizard_selected_rel',
        'wizard_id',
        'dp_id',
        string='Select DP Requests to Assign',
        domain="[('id', 'in', available_dp_ids)]"
    )

    # ============================================================
    # TOTALS
    # ============================================================

    selected_total = fields.Monetary(
        string='Selected Total',
        compute='_compute_selected_totals',
        currency_field='currency_id'
    )

    selected_count = fields.Integer(
        string='Selected Count',
        compute='_compute_selected_totals'
    )

    new_dp_total = fields.Monetary(
        string='New DP Total',
        compute='_compute_selected_totals',
        currency_field='currency_id',
        help='Current + Selected'
    )

    new_difference = fields.Monetary(
        string='New Difference',
        compute='_compute_selected_totals',
        currency_field='currency_id',
        help='Payment Amount - New DP Total'
    )

    show_warning = fields.Boolean(
        compute='_compute_selected_totals'
    )

    # ============================================================
    # COMPUTED
    # ============================================================

    @api.depends('partner_id', 'currency_id', 'payment_type')
    def _compute_available_dps(self):
        for wiz in self:
            if not all([wiz.partner_id, wiz.currency_id, wiz.payment_type]):
                wiz.available_dp_ids = False
                wiz.available_count = 0
                continue

            domain = [
                ('state', '=', 'pending'),
                ('is_allocated', '=', False),
                ('partner_id', '=', wiz.partner_id.id),
                ('currency_id', '=', wiz.currency_id.id),
                ('payment_type', '=', wiz.payment_type),
            ]
            available = self.env['dm.downpayment.request'].search(domain)
            wiz.available_dp_ids = [(6, 0, available.ids)]
            wiz.available_count = len(available)

    @api.depends('selected_dp_ids', 'current_dp_total', 'payment_amount')
    def _compute_selected_totals(self):
        for wiz in self:
            wiz.selected_count = len(wiz.selected_dp_ids)
            wiz.selected_total = sum(wiz.selected_dp_ids.mapped('amount_requested'))
            wiz.new_dp_total = wiz.current_dp_total + wiz.selected_total
            wiz.new_difference = wiz.payment_amount - wiz.new_dp_total
            wiz.show_warning = abs(wiz.new_difference) > 0.01

    # ============================================================
    # ACTIONS
    # ============================================================

    def action_assign(self):
        """Assign selected DPs to payment"""
        self.ensure_one()

        if not self.selected_dp_ids:
            raise UserError(_("No DP requests selected."))

        # Re-validate payment is still draft
        if self.payment_id.state != 'draft':
            raise UserError(_(
                "Payment '%s' is no longer in draft state.\n"
                "Cannot assign DP requests to posted payments."
            ) % self.payment_id.name)

        # Re-validate DPs are still available
        unavailable = self.selected_dp_ids.filtered(
            lambda dp: dp.state != 'pending' or dp.is_allocated
        )
        if unavailable:
            raise UserError(_(
                "The following DP requests are no longer available:\n%s"
            ) % ', '.join(unavailable.mapped('name')))

        # Assign
        self.selected_dp_ids.with_context(force_dp_write=True).write({
            'payment_id': self.payment_id.id
        })

        _logger.info(
            "Assigned %d DP requests to payment %s: %s",
            len(self.selected_dp_ids),
            self.payment_id.name,
            ', '.join(self.selected_dp_ids.mapped('name'))
        )

        # Log on payment chatter
        dp_list = '\n'.join([
            f"• {dp.name}: {dp.amount_requested:,.2f} {dp.currency_id.name}"
            for dp in self.selected_dp_ids
        ])
        self.payment_id.message_post(
            body=_(
                "DP Requests assigned:\n%s\n\n"
                "New Total: %s %s"
            ) % (dp_list, f"{self.new_dp_total:,.2f}", self.currency_id.name),
            message_type='comment'
        )

        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        """Close wizard without action"""
        return {'type': 'ir.actions.act_window_close'}