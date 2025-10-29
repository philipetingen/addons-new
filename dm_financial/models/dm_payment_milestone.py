# -*- coding: utf-8 -*-
"""
Payment Milestone Transaction Management
Tracks payment milestones for specific deals
"""

from odoo import api, fields, models
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmPaymentMilestone(models.Model):
    _name = 'dm.payment.milestone'
    _description = 'Deal Payment Milestone Instance'
    _order = 'deal_id, sequence, due_date'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    # Link to Master Data
    milestone_type_id = fields.Many2one(
        'dm.milestone.type',
        string='Milestone Type',
        required=True,
        ondelete='restrict',
        tracking=True
    )
    
    # Basic Information
    name = fields.Char(
        string='Milestone Name',
        compute='_compute_name',
        store=True
    )
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    payment_type = fields.Selection([
        ('customer', 'Customer Payment'),
        ('supplier', 'Supplier Payment')
    ], string='Payment Type', required=True, tracking=True)
    
    sequence = fields.Integer(
        string='Sequence',
        related='milestone_type_id.sequence',
        store=True
    )
    
    # Amounts
    percentage = fields.Float(
        string='Percentage',
        digits=(5, 2),
        help='Percentage of deal value for this milestone'
    )
    
    fixed_amount = fields.Float(
        string='Fixed Amount',
        digits=(16, 2),
        help='Fixed amount override'
    )
    
    amount = fields.Monetary(
        string='Amount',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id'
    )
    
    amount_paid = fields.Monetary(
        string='Amount Paid',
        currency_field='currency_id',
        tracking=True
    )
    
    amount_remaining = fields.Monetary(
        string='Amount Remaining',
        compute='_compute_amount_remaining',
        store=True,
        currency_field='currency_id'
    )
    
    # Dates
    milestone_date = fields.Date(
        string='Milestone Date',
        compute='_compute_milestone_date',
        store=True,
        help='Date when milestone event occurs'
    )
    
    timing = fields.Selection([
        ('before', 'Before'),
        ('on', 'On'),
        ('after', 'After')
    ], string='Payment Timing',
       default='on',
       required=True)
    
    days_offset = fields.Integer(
        string='Days Offset',
        default=0,
        help='Days before/after milestone for payment'
    )
    
    due_date = fields.Date(
        string='Payment Due Date',
        compute='_compute_due_date',
        store=True,
        tracking=True
    )
    
    # Status
    state = fields.Selection([
        ('pending', 'Pending'),
        ('due', 'Due'),
        ('requested', 'DP Requested'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], default='pending', tracking=True, required=True)
    
    # Related Fields
    currency_id = fields.Many2one(
        'res.currency',
        related='deal_id.currency_id',
        store=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        compute='_compute_partner',
        store=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        related='deal_id.company_id',
        store=True
    )
    
    # Payment Records
    downpayment_request_ids = fields.One2many(
        'dm.downpayment.request',
        'milestone_id',
        string='Downpayment Requests'
    )
    
    downpayment_count = fields.Integer(
        string='DP Count',
        compute='_compute_dp_count'
    )
    
    # Master Data References
    milestone_code = fields.Char(
        related='milestone_type_id.milestone_code',
        string='Milestone Code',
        store=True
    )
    
    is_payment_trigger = fields.Boolean(
        related='milestone_type_id.is_payment_trigger',
        string='Payment Trigger'
    )
    
    @api.depends('milestone_type_id.name', 'payment_type', 'percentage')
    def _compute_name(self):
        for milestone in self:
            type_label = 'Customer' if milestone.payment_type == 'customer' else 'Supplier'
            milestone_name = milestone.milestone_type_id.name if milestone.milestone_type_id else 'Milestone'
            
            if milestone.percentage:
                milestone.name = f"{type_label} - {milestone_name} ({milestone.percentage}%)"
            else:
                milestone.name = f"{type_label} - {milestone_name}"
    
    @api.depends('payment_type', 'deal_id.customer_id', 'deal_id.supplier_id')
    def _compute_partner(self):
        for milestone in self:
            if milestone.payment_type == 'customer':
                milestone.partner_id = milestone.deal_id.customer_id
            else:
                milestone.partner_id = milestone.deal_id.supplier_id
    
    @api.depends('milestone_type_id', 'deal_id')
    def _compute_milestone_date(self):
        """Calculate milestone date from deal using type's field mapping"""
        for milestone in self:
            if milestone.milestone_type_id and milestone.deal_id:
                milestone.milestone_date = milestone.milestone_type_id.get_milestone_date(
                    milestone.deal_id
                )
            else:
                milestone.milestone_date = False
    
    @api.depends('milestone_date', 'timing', 'days_offset')
    def _compute_due_date(self):
        for milestone in self:
            if not milestone.milestone_date:
                milestone.due_date = False
                continue
            
            # Calculate offset based on timing
            if milestone.timing == 'before':
                offset_days = -abs(milestone.days_offset)
            elif milestone.timing == 'after':
                offset_days = abs(milestone.days_offset)
            else:  # 'on'
                offset_days = 0
            
            milestone.due_date = milestone.milestone_date + timedelta(days=offset_days)
    
    @api.depends('percentage', 'fixed_amount', 'deal_id', 'payment_type')
    def _compute_amount(self):
        for milestone in self:
            if milestone.fixed_amount:
                milestone.amount = milestone.fixed_amount
            elif milestone.percentage and milestone.deal_id:
                # Get base amount depending on payment type
                if milestone.payment_type == 'customer':
                    base_amount = milestone.deal_id.total_sale_amount or 0
                else:
                    base_amount = milestone.deal_id.total_purchase_amount or 0
                
                milestone.amount = base_amount * (milestone.percentage / 100.0)
            else:
                milestone.amount = 0.0
    
    @api.depends('amount', 'amount_paid')
    def _compute_amount_remaining(self):
        for milestone in self:
            milestone.amount_remaining = milestone.amount - milestone.amount_paid
    
    def _compute_dp_count(self):
        for milestone in self:
            milestone.downpayment_count = len(milestone.downpayment_request_ids)
    
    def action_create_downpayment(self):
        """Create downpayment request for this milestone"""
        self.ensure_one()
        
        if self.amount_remaining <= 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Payment Needed',
                    'message': 'This milestone has been fully paid.',
                    'type': 'warning',
                }
            }
        
        # Create downpayment request
        dp_vals = {
            'deal_id': self.deal_id.id,
            'milestone_id': self.id,
            'request_type': self.payment_type,
            'partner_id': self.partner_id.id,
            'percentage': self.percentage,
            'amount_requested': self.amount_remaining,
            'due_date': self.due_date or fields.Date.today(),
        }
        
        downpayment = self.env['dm.downpayment.request'].create(dp_vals)
        
        # Update milestone state
        self.state = 'requested'
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Downpayment Request',
            'res_model': 'dm.downpayment.request',
            'res_id': downpayment.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_downpayments(self):
        """View all downpayment requests for this milestone"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Downpayment Requests',
            'res_model': 'dm.downpayment.request',
            'domain': [('milestone_id', '=', self.id)],
            'view_mode': 'tree,form',
            'context': {
                'default_milestone_id': self.id,
                'default_deal_id': self.deal_id.id,
                'default_request_type': self.payment_type,
                'default_partner_id': self.partner_id.id,
            }
        }
    
    def update_payment_status(self):
        """Update milestone status based on payments"""
        for milestone in self:
            total_paid = sum(milestone.downpayment_request_ids.filtered(
                lambda dp: dp.state == 'paid'
            ).mapped('amount_received'))
            
            milestone.amount_paid = total_paid
            
            if milestone.amount_paid >= milestone.amount:
                milestone.state = 'paid'
            elif milestone.amount_paid > 0:
                milestone.state = 'partial'
            elif milestone.downpayment_request_ids.filtered(lambda dp: dp.state != 'cancelled'):
                milestone.state = 'requested'
            else:
                milestone.state = 'pending'
    
    @api.model
    def check_due_milestones(self):
        """Cron job to check and update milestone due status"""
        today = fields.Date.today()
        pending_milestones = self.search([
            ('state', '=', 'pending'),
            ('due_date', '<=', today)
        ])
        
        for milestone in pending_milestones:
            milestone.state = 'due'
            milestone.message_post(
                body=f"Payment milestone is now due: {milestone.name}",
                subtype_xmlid='mail.mt_note'
            )


class DmDeal(models.Model):
    _inherit = 'dm.deal'
    
    # Payment Milestones
    payment_milestone_ids = fields.One2many(
        'dm.payment.milestone',
        'deal_id',
        string='Payment Milestones'
    )
    
    payment_milestone_count = fields.Integer(
        string='Milestone Count',
        compute='_compute_payment_milestone_count'
    )
    
    next_milestone_date = fields.Date(
        string='Next Payment Due',
        compute='_compute_next_milestone',
        store=True
    )
    
    payment_progress = fields.Float(
        string='Payment Progress %',
        compute='_compute_payment_progress',
        store=True
    )
    
    def _compute_payment_milestone_count(self):
        for deal in self:
            deal.payment_milestone_count = len(deal.payment_milestone_ids)
    
    @api.depends('payment_milestone_ids.state', 'payment_milestone_ids.due_date')
    def _compute_next_milestone(self):
        for deal in self:
            pending = deal.payment_milestone_ids.filtered(
                lambda m: m.state in ['pending', 'due', 'requested']
            ).sorted('due_date')
            
            deal.next_milestone_date = pending[0].due_date if pending else False
    
    @api.depends('payment_milestone_ids.amount', 'payment_milestone_ids.amount_paid')
    def _compute_payment_progress(self):
        for deal in self:
            total = sum(deal.payment_milestone_ids.mapped('amount'))
            paid = sum(deal.payment_milestone_ids.mapped('amount_paid'))
            
            deal.payment_progress = (paid / total * 100) if total > 0 else 0.0
    
    def action_view_payment_milestones(self):
        """View payment milestones for this deal"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Payment Milestones',
            'res_model': 'dm.payment.milestone',
            'domain': [('deal_id', '=', self.id)],
            'view_mode': 'tree,form,kanban',
            'context': {
                'default_deal_id': self.id,
                'group_by': ['payment_type']
            }
        }
    
    def action_generate_milestones(self):
        """Generate payment milestones from payment terms"""
        self.ensure_one()
        
        # Clear existing milestones
        self.payment_milestone_ids.unlink()
        
        # This would integrate with payment terms in future
        # For now, create basic milestones
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Milestones Generated',
                'message': f'Created {len(self.payment_milestone_ids)} payment milestones',
                'type': 'success',
            }
        }