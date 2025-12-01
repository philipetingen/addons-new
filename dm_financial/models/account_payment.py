# -*- coding: utf-8 -*-
"""
Account Payment Extension for DM Financial
Links payments to DP Requests with M:1 relationship

Design:
- DP Requests are analytical/business layer
- account.payment is financial/accounting layer
- Multiple DPs can link to one Payment
- Payment posting triggers DP state → paid
- Cancellation blocked when DPs allocated
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # ============================================================
    # DP REQUEST LINKAGE
    # ============================================================

    dp_request_ids = fields.One2many(
        'dm.downpayment.request',
        'payment_id',
        string='DP Requests',
        help='Downpayment requests allocated to this payment'
    )

    dp_request_count = fields.Integer(
        string='DP Count',
        compute='_compute_dp_request_info',
        store=True
    )

    dp_total_amount = fields.Monetary(
        string='Total DP Amount',
        compute='_compute_dp_request_info',
        store=True,
        currency_field='currency_id',
        help='Sum of allocated DP request amounts'
    )

    has_dp_requests = fields.Boolean(
        string='Has DP Requests',
        compute='_compute_dp_request_info',
        store=True,
        help='Technical field to control cancellation'
    )

    dp_amount_difference = fields.Monetary(
        string='DP Difference',
        compute='_compute_dp_request_info',
        store=True,
        currency_field='currency_id',
        help='Payment amount minus DP total (positive = overpayment)'
    )

    # ============================================================
    # DEAL REFERENCE (for traceability)
    # ============================================================

    dm_deal_ids = fields.Many2many(
        'dm.deal',
        string='Related Deals',
        compute='_compute_dm_deal_ids',
        store=True,
        help='Deals linked through DP requests'
    )

    dm_deal_count = fields.Integer(
        string='Deal Count',
        compute='_compute_dm_deal_ids',
        store=True
    )

    # ============================================================
    # COMPUTE METHODS
    # ============================================================

    @api.depends('dp_request_ids', 'dp_request_ids.amount_requested', 'amount')
    def _compute_dp_request_info(self):
        for payment in self:
            dp_requests = payment.dp_request_ids
            payment.dp_request_count = len(dp_requests)
            payment.has_dp_requests = bool(dp_requests)
            payment.dp_total_amount = sum(dp_requests.mapped('amount_requested'))
            payment.dp_amount_difference = payment.amount - payment.dp_total_amount

    @api.depends('dp_request_ids', 'dp_request_ids.deal_id')
    def _compute_dm_deal_ids(self):
        for payment in self:
            deals = payment.dp_request_ids.mapped('deal_id')
            payment.dm_deal_ids = [(6, 0, deals.ids)]
            payment.dm_deal_count = len(deals)

    # ============================================================
    # BUSINESS LOGIC OVERRIDES
    # ============================================================

    def action_cancel(self):
        """Block cancellation if DP requests are linked"""
        for payment in self:
            if payment.has_dp_requests:
                dp_names = ', '.join(payment.dp_request_ids.mapped('name'))
                raise UserError(_(
                    "Cannot cancel payment with allocated DP Requests.\n\n"
                    "Deallocate the following first:\n%s\n\n"
                    "Go to each DP Request and click 'Deallocate', "
                    "or remove them from this payment's DP Requests tab."
                ) % dp_names)
        return super().action_cancel()

    def action_draft(self):
        """Block reset to draft if DP requests are paid"""
        for payment in self:
            paid_dps = payment.dp_request_ids.filtered(lambda dp: dp.state == 'paid')
            if paid_dps:
                raise UserError(_(
                    "Cannot reset to draft. The following DP Requests "
                    "are marked as paid:\n%s\n\n"
                    "Deallocate them first, which will revert their state to 'Pending'."
                ) % ', '.join(paid_dps.mapped('name')))
        return super().action_draft()

    def action_post(self):
        """When payment is posted, mark linked DPs as paid"""
        res = super().action_post()

        for payment in self:
            pending_dps = payment.dp_request_ids.filtered(
                lambda dp: dp.state == 'pending'
            )
            if pending_dps:
                pending_dps.with_context(
                    from_payment_post=True,
                    force_dp_write=True
                ).write({'state': 'paid'})

                _logger.info(
                    "Payment %s posted - marked %d DP requests as paid: %s",
                    payment.name,
                    len(pending_dps),
                    ', '.join(pending_dps.mapped('name'))
                )

        return res

    def unlink(self):
        """Block deletion if DP requests linked (ondelete=restrict handles this, 
        but provide better error message)"""
        for payment in self:
            if payment.has_dp_requests:
                raise UserError(_(
                    "Cannot delete payment '%s' with allocated DP Requests.\n"
                    "Deallocate the following first:\n%s"
                ) % (payment.name, ', '.join(payment.dp_request_ids.mapped('name'))))
        return super().unlink()

    # ============================================================
    # ACTIONS
    # ============================================================

    def action_view_dp_requests(self):
        """Smart button to view linked DP requests"""
        self.ensure_one()

        action = {
            'type': 'ir.actions.act_window',
            'name': _('DP Requests'),
            'res_model': 'dm.downpayment.request',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.dp_request_ids.ids)],
            'context': {
                'default_payment_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_currency_id': self.currency_id.id,
                'default_payment_type': self.payment_type,
            },
        }

        if len(self.dp_request_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.dp_request_ids.id

        return action

    def action_view_deals(self):
        """Smart button to view related deals"""
        self.ensure_one()

        action = {
            'type': 'ir.actions.act_window',
            'name': _('Related Deals'),
            'res_model': 'dm.deal',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.dm_deal_ids.ids)],
        }

        if len(self.dm_deal_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.dm_deal_ids.id

        return action

    def action_assign_dp_requests(self):
        """Open wizard to assign additional DP requests"""
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(_(
                "Can only assign DP requests to draft payments.\n"
                "Current payment state: %s"
            ) % self.state)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Assign DP Requests'),
            'res_model': 'dm.dp.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_currency_id': self.currency_id.id,
                'default_payment_type': self.payment_type,
            },
        }

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _get_dp_summary(self):
        """Get summary string of linked DPs for logging/display"""
        self.ensure_one()
        if not self.dp_request_ids:
            return "No DP Requests"

        lines = []
        for dp in self.dp_request_ids:
            lines.append(f"  - {dp.name}: {dp.amount_requested} {dp.currency_id.name}")

        return (
            f"DP Requests ({self.dp_request_count}):\n"
            + '\n'.join(lines)
            + f"\nTotal: {self.dp_total_amount} {self.currency_id.name}"
        )