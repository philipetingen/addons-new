from odoo import models, fields, api
from datetime import timedelta


class DmCashFlow(models.Model):
    _name = 'dm.cash_flow'
    _description = 'Cash Flow Projection'
    _order = 'date, id'
    _inherit = ['mail.thread']
    
    # Deal reference
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    # Date and type
    date = fields.Date(
        string='Date',
        required=True,
        tracking=True,
        index=True
    )
    
    type = fields.Selection([
        ('inflow', 'Inflow'),
        ('outflow', 'Outflow')
    ], string='Type', required=True, tracking=True)
    
    category = fields.Selection([
        ('customer_payment', 'Customer Payment'),
        ('supplier_payment', 'Supplier Payment'),
        ('freight_payment', 'Freight Payment'),
        ('insurance_payment', 'Insurance Payment'),
        ('other', 'Other')
    ], string='Category', required=True)
    
    # Description
    description = fields.Char(
        string='Description',
        required=True
    )
    
    # Amounts
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        tracking=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True
    )
    
    # Status
    status = fields.Selection([
        ('projected', 'Projected'),
        ('confirmed', 'Confirmed'),
        ('received', 'Received/Paid'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='projected', tracking=True)
    
    # Related actual payment
    payment_id = fields.Many2one(
        'account.payment',
        string='Actual Payment'
    )
    
    invoice_id = fields.Many2one(
        'account.move',
        string='Related Invoice'
    )
    
    # Running balance (computed)
    running_balance = fields.Monetary(
        string='Running Balance',
        currency_field='currency_id',
        compute='_compute_running_balance'
    )
    
    @api.depends('deal_id', 'date', 'type', 'amount')
    def _compute_running_balance(self):
        """Compute running balance for cash flow"""
        for record in self:
            balance = 0
            # Get all previous cash flows for this deal
            previous = self.search([
                ('deal_id', '=', record.deal_id.id),
                ('date', '<=', record.date),
                ('id', '<=', record.id)
            ])
            
            for cf in previous:
                if cf.type == 'inflow':
                    balance += cf.amount
                else:
                    balance -= cf.amount
            
            record.running_balance = balance
    
    def action_confirm(self):
        """Confirm projected cash flow"""
        self.ensure_one()
        self.status = 'confirmed'
    
    def action_mark_received(self):
        """Mark as received/paid"""
        self.ensure_one()
        self.status = 'received'