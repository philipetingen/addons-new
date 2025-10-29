# -*- coding: utf-8 -*-
"""
Milestone Type Master Data
Defines available milestone types for payment and operational tracking
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DmMilestoneType(models.Model):
    _name = 'dm.milestone.type'
    _description = 'Milestone Type Configuration'
    _order = 'sequence, name'
    _rec_name = 'name'
    
    # Basic Information
    name = fields.Char(
        string='Milestone Name',
        required=True,
        translate=True,
        help='Display name of the milestone'
    )
    
    milestone_code = fields.Char(
        string='Code',
        required=True,
        index=True,
        help='Unique code for programmatic reference'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order in which milestones typically occur'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    # Milestone Characteristics
    is_payment_trigger = fields.Boolean(
        string='Payment Trigger',
        default=True,
        help='This milestone can trigger payment due dates'
    )
    
    is_customer_visible = fields.Boolean(
        string='Customer Visible',
        default=True,
        help='Milestone is visible to customers in tracking'
    )
    
    typical_days_from_order = fields.Integer(
        string='Typical Days from Order',
        help='Typical number of days from order confirmation to this milestone'
    )
    
    # Deal Field Mapping (for date calculation)
    deal_date_field = fields.Char(
        string='Deal Date Field',
        help='Field name on dm.deal for this milestone date'
    )
    
    primary_date_field = fields.Char(
        string='Primary Date Field',
        help='Primary date field to use (e.g., rts_actual)'
    )
    
    fallback_date_field = fields.Char(
        string='Fallback Date Field',
        help='Fallback date field if primary is empty (e.g., rts_current)'
    )
    
    # Milestone Categorization
    milestone_type = fields.Selection([
        ('order', 'Order'),
        ('production', 'Production'),
        ('shipping', 'Shipping'),
        ('delivery', 'Delivery'),
        ('document', 'Document')
    ], string='Category', required=True, default='order')
    
    # Default Timing Configuration
    default_timing = fields.Selection([
        ('before', 'Before'),
        ('on', 'On'),
        ('after', 'After')
    ], string='Default Timing', default='on',
       help='When payment is typically due relative to milestone')
    
    default_days = fields.Integer(
        string='Default Days Offset',
        default=0,
        help='Default number of days before/after milestone for payment'
    )
    
    # Special Flags
    requires_confirmation = fields.Boolean(
        string='Requires Confirmation',
        default=False,
        help='Milestone requires explicit confirmation (e.g., loading confirmation)'
    )
    
    blocking_milestone = fields.Boolean(
        string='Blocking Milestone',
        default=False,
        help='Process cannot continue until this milestone is complete'
    )
    
    description = fields.Text(
        string='Description',
        translate=True,
        help='Detailed description of this milestone'
    )
    
    # Usage Tracking
    payment_term_count = fields.Integer(
        string='Payment Terms Using',
        compute='_compute_usage_count',
        help='Number of payment terms using this milestone'
    )
    
    _sql_constraints = [
        ('code_unique', 'UNIQUE(milestone_code)', 'Milestone code must be unique!')
    ]
    
    def _compute_usage_count(self):
        """Count payment terms using this milestone"""
        PaymentTermLine = self.env['account.payment.term.line']
        for milestone in self:
            milestone.payment_term_count = PaymentTermLine.search_count([
                ('milestone_id', '=', milestone.id)
            ])
    
    @api.constrains('milestone_code')
    def _check_milestone_code(self):
        """Validate milestone code format"""
        for milestone in self:
            if milestone.milestone_code:
                # Code should be lowercase with underscores
                if not milestone.milestone_code.replace('_', '').isalnum():
                    raise ValidationError(
                        'Milestone code must contain only letters, numbers, and underscores'
                    )
    
    def get_milestone_date(self, deal):
        """
        Calculate milestone date from deal based on field mapping.
        
        Args:
            deal: dm.deal record
            
        Returns:
            date: Calculated milestone date or False
        """
        self.ensure_one()
        
        # Try primary date field
        if self.primary_date_field and hasattr(deal, self.primary_date_field):
            date_value = getattr(deal, self.primary_date_field)
            if date_value:
                return date_value
        
        # Try fallback date field
        if self.fallback_date_field and hasattr(deal, self.fallback_date_field):
            date_value = getattr(deal, self.fallback_date_field)
            if date_value:
                return date_value
        
        # Try generic deal date field
        if self.deal_date_field and hasattr(deal, self.deal_date_field):
            date_value = getattr(deal, self.deal_date_field)
            if date_value:
                return date_value
        
        return False
    
    def action_view_payment_terms(self):
        """View payment terms using this milestone"""
        self.ensure_one()
        
        # Find payment term lines using this milestone
        lines = self.env['account.payment.term.line'].search([
            ('milestone_id', '=', self.id)
        ])
        
        # Get unique payment terms
        payment_term_ids = lines.mapped('payment_id').ids
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Payment Terms using {self.name}',
            'res_model': 'account.payment.term',
            'domain': [('id', 'in', payment_term_ids)],
            'view_mode': 'tree,form',
            'context': {'create': False}
        }