# dm_deal/models/dm_allocation.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmAllocation(models.Model):
    """
    Allocation tracking for deals to production runs and shipments.
    """
    _name = 'dm.allocation'
    _description = 'Deal Allocation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'allocation_date desc, id desc'
    
    # =========================================================================
    # CORE FIELDS
    # =========================================================================
    
    name = fields.Char(
        string='Allocation Reference',
        required=True,
        index=True,
        default='New',
        readonly=True
    )
    
    # REMOVED: display_name field - not needed with name_get()
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        index=True,
        ondelete='cascade',
        tracking=True
    )
    
    allocation_type = fields.Selection([
        ('production', 'Production'),
        ('shipment', 'Shipment'),
    ], string='Type', required=True, tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='draft', required=True, tracking=True)
    
    allocation_date = fields.Datetime(
        string='Allocation Date',
        default=fields.Datetime.now,
        tracking=True
    )
    
    completion_date = fields.Datetime(
        string='Completion Date',
        readonly=True,
        tracking=True
    )
    
    notes = fields.Text(string='Notes')
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    # =========================================================================
    # DISPLAY NAME - Handled by name_get()
    # =========================================================================
    # REMOVED: _compute_display_name method - not needed
    
    def name_get(self):
        """Custom display name - Odoo 17 uses this for display_name automatically"""
        result = []
        for rec in self:
            if rec.name and rec.name != 'New':
                name = rec.name
            elif rec.deal_id:
                type_label = 'Production' if rec.allocation_type == 'production' else 'Shipment'
                name = f"{rec.deal_id.name} → {type_label}"
            else:
                name = f"Allocation #{rec.id}" if rec.id else "New Allocation"
            result.append((rec.id, name))
        return result
    
    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        """Enable search by deal name"""
        args = list(args or [])
        if name:
            args += ['|', ('name', operator, name), ('deal_id.name', operator, name)]
        return self._search(args, limit=limit, access_rights_uid=name_get_uid)
    
    # =========================================================================
    # CONSTRAINTS
    # =========================================================================
    
    @api.constrains('deal_id', 'allocation_type', 'state')
    def _check_unique_active_allocation(self):
        """Ensure a deal can only have ONE active allocation per type"""
        for rec in self:
            if rec.state == 'active':
                existing = self.search([
                    ('deal_id', '=', rec.deal_id.id),
                    ('allocation_type', '=', rec.allocation_type),
                    ('state', '=', 'active'),
                    ('id', '!=', rec.id),
                ])
                if existing:
                    raise ValidationError(_(
                        f"Deal {rec.deal_id.name} is already allocated to "
                        f"{rec.allocation_type}. Cannot create duplicate active allocation."
                    ))
    
    # =========================================================================
    # WORKFLOW ACTIONS
    # =========================================================================
    
    def action_activate(self):
        """Activate the allocation"""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft allocations can be activated'))
            rec.state = 'active'
            rec.allocation_date = fields.Datetime.now()
            _logger.info(f"Activated allocation: {rec.name}")
    
    def action_complete(self):
        """Mark allocation as completed"""
        for rec in self:
            if rec.state != 'active':
                raise UserError(_('Only active allocations can be completed'))
            rec.state = 'completed'
            rec.completion_date = fields.Datetime.now()
            _logger.info(f"Completed allocation: {rec.name}")
    
    def action_cancel(self):
        """Cancel the allocation and free the deal"""
        for rec in self:
            if rec.state == 'completed':
                raise UserError(_('Cannot cancel completed allocations'))
            
            old_state = rec.state
            rec.state = 'cancelled'
            
            # Update deal state if needed
            if old_state == 'active' and rec.deal_id:
                deal = rec.deal_id
                other_active = self.search([
                    ('deal_id', '=', deal.id),
                    ('state', '=', 'active'),
                    ('id', '!=', rec.id),
                ])
                
                if not other_active and deal.state in ['allocated', 'partial', 'ready', 'shipping']:
                    deal.state = 'confirmed'
                    _logger.info(f"Deal {deal.name} reset to 'confirmed'")
            
            _logger.info(f"Cancelled allocation: {rec.name}")
    
    # =========================================================================
    # ORM OVERRIDES
    # =========================================================================
    
    @api.model
    def create(self, vals):
        """Generate name and log creation"""
        # Generate name
        if vals.get('name', 'New') == 'New':
            deal = self.env['dm.deal'].browse(vals.get('deal_id'))
            alloc_type = vals.get('allocation_type', '')
            type_label = 'Production' if alloc_type == 'production' else 'Shipment'
            vals['name'] = f"{deal.name} → {type_label}" if deal else "New Allocation"
        
        allocation = super().create(vals)
        
        if allocation.deal_id:
            allocation.deal_id.message_post(
                body=_(f"Allocation created: {allocation.name}"),
                subtype_xmlid='mail.mt_note'
            )
        
        return allocation
    
    def write(self, vals):
        """Track state changes"""
        result = super().write(vals)
        
        if 'state' in vals:
            for rec in self:
                if rec.deal_id:
                    rec.deal_id.message_post(
                        body=_(f"Allocation {rec.name} → {rec.state}"),
                        subtype_xmlid='mail.mt_note'
                    )
        
        return result
    
    def unlink(self):
        """Prevent deletion of active allocations"""
        if any(rec.state == 'active' for rec in self):
            raise UserError(_('Cannot delete active allocations. Cancel them first.'))
        return super().unlink()