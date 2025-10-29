# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmShipment(models.Model):
    """
    Shipment - BLACK BOX Implementation
    
    Minimal model serving as allocation target for deals.
    Business logic to be expanded in future iterations.
    """
    _name = 'dm.shipment'
    _description = 'Shipment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    
    # ========================================================================
    # CORE FIELDS
    # ========================================================================
    
    name = fields.Char(
        string='Shipment',
        required=True,
        copy=False,
        default='New',
        tracking=True
    )
    
    loading_port_id = fields.Many2one(
        'dm.port',
        string='Loading Port',
        required=True,
        tracking=True
    )
    
    discharge_port_id = fields.Many2one(
        'dm.port',
        string='Discharge Port',
        required=True,
        tracking=True
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('loading', 'Loading'),
        ('shipped', 'Shipped'),
        ('arrived', 'Arrived'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    # ========================================================================
    # DATE FIELDS (Minimal - uses deal milestone dates)
    # ========================================================================
    
    loading_date = fields.Date(
        string='Loading Date',
        tracking=True
    )
    
    etd = fields.Date(
        string='ETD (Estimated Time of Departure)',
        tracking=True
    )
    
    eta = fields.Date(
        string='ETA (Estimated Time of Arrival)',
        tracking=True
    )
    
    # ========================================================================
    # ALLOCATION RELATIONSHIPS
    # ========================================================================
    
    allocation_ids = fields.One2many(
        'dm.allocation',
        'shipment_id',
        string='Deal Allocations',
        help='Deals allocated to this shipment'
    )
    
    deal_ids = fields.Many2many(
        'dm.deal',
        compute='_compute_deals',
        string='Deals',
        help='Deals in this shipment'
    )
    
    deal_count = fields.Integer(
        compute='_compute_deal_count',
        string='Deal Count'
    )
    
    # ========================================================================
    # NOTES
    # ========================================================================
    
    notes = fields.Text(string='Notes')
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('allocation_ids', 'allocation_ids.deal_id')
    def _compute_deals(self):
        """Get deals from allocations"""
        for shipment in self:
            active_allocations = shipment.allocation_ids.filtered(
                lambda a: a.state in ['active', 'completed']
            )
            shipment.deal_ids = active_allocations.mapped('deal_id')
    
    @api.depends('deal_ids')
    def _compute_deal_count(self):
        for shipment in self:
            shipment.deal_count = len(shipment.deal_ids)
    
    # ========================================================================
    # CRUD METHODS
    # ========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        """Generate sequence for name"""
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'dm.shipment'
                ) or 'New'
        return super().create(vals_list)
    
    # ========================================================================
    # STATE MANAGEMENT (Minimal)
    # ========================================================================
    
    def action_confirm(self):
        """Confirm shipment"""
        self.write({'state': 'confirmed'})
        return True
    
    def action_start_loading(self):
        """
        Start loading process.
        BLOCKED if any production run is not ready.
        """
        for shipment in self:
            # Validate all production is ready
            if not shipment._all_production_ready():
                # Get details for error message
                not_ready = []
                for deal in shipment.deal_ids:
                    pr_allocs = deal.allocation_ids.filtered(
                        lambda a: a.allocation_type == 'production' 
                        and a.state in ['active', 'completed']
                    )
                    for alloc in pr_allocs:
                        if alloc.production_run_id and alloc.production_run_id.state not in ['ready', 'done']:
                            not_ready.append(
                                f"  • Deal {deal.name}: PR {alloc.production_run_id.name} "
                                f"({alloc.production_run_id.state})"
                            )
                
                raise UserError(_(
                    'Cannot start loading: Production not ready!\n\n'
                    'The following production runs must be marked as "Ready" first:\n\n'
                    '%s\n\n'
                    'Please complete production before loading.'
                ) % '\n'.join(not_ready))
            
            shipment.write({'state': 'loading'})
            
            _logger.info(
                f"Shipment {shipment.name} - Loading started "
                f"({len(shipment.deal_ids)} deals)"
            )
        
        return True
    
    def _all_production_ready(self):
        """
        Check if all production runs for deals in this shipment are ready.
        
        Returns:
            bool: True if all PRs are in 'ready' or 'done' state
        """
        self.ensure_one()
        
        for deal in self.deal_ids:
            # Get production allocations for this deal
            pr_allocs = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'production' 
                and a.state in ['active', 'completed']
            )
            
            # Check each production run
            for alloc in pr_allocs:
                if not alloc.production_run_id:
                    _logger.warning(
                        f"Shipment {self.name}: Deal {deal.name} allocation "
                        f"{alloc.id} has no production_run_id"
                    )
                    return False
                
                if alloc.production_run_id.state not in ['ready', 'done']:
                    _logger.info(
                        f"Shipment {self.name}: Deal {deal.name} has PR "
                        f"{alloc.production_run_id.name} in state "
                        f"'{alloc.production_run_id.state}' (not ready)"
                    )
                    return False
        
        return True
    
    def action_ship(self):
        """
        Mark shipment as shipped (departed).
        Updates deal states to 'shipping'.
        """
        for shipment in self:
            shipment.write({'state': 'shipped'})
            
            # Update deal states
            for alloc in shipment.allocation_ids.filtered(
                lambda a: a.state in ['active', 'completed']
            ):
                deal = alloc.deal_id
                if hasattr(deal, '_compute_deal_state_from_allocations'):
                    deal._compute_deal_state_from_allocations()
                    _logger.info(
                        f"Shipment {shipment.name} shipped → "
                        f"Deal {deal.name} updated to '{deal.state}'"
                    )
            
            _logger.info(f"Shipment {shipment.name} marked as shipped")
        
        return True
    
    def action_arrive(self):
        """
        Mark shipment as arrived at POD.
        Deal remains in 'shipping' state (no state change).
        """
        for shipment in self:
            shipment.write({'state': 'arrived'})
            
            _logger.info(
                f"Shipment {shipment.name} arrived at "
                f"{shipment.discharge_port_id.name if shipment.discharge_port_id else 'destination'}"
            )
            
            # Note: Deal state stays 'shipping' - no update needed
        
        return True
    
    def action_deliver(self):
        """
        Mark shipment as delivered (all procedures completed).
        Completes allocations and automatically updates deal states to 'delivered'.
        """
        for shipment in self:
            shipment.write({'state': 'delivered'})
            
            # Complete allocations
            active_allocs = shipment.allocation_ids.filtered(lambda a: a.state == 'active')
            if active_allocs:
                active_allocs.action_complete()
                _logger.info(
                    f"Shipment {shipment.name} delivered → "
                    f"{len(active_allocs)} allocations completed"
                )
            
            # Update deal states to 'delivered' (automatic)
            for alloc in shipment.allocation_ids:
                deal = alloc.deal_id
                if hasattr(deal, '_compute_deal_state_from_allocations'):
                    deal._compute_deal_state_from_allocations()
                    _logger.info(
                        f"Shipment {shipment.name} delivered → "
                        f"Deal {deal.name} updated to '{deal.state}'"
                    )
            
            _logger.info(f"Shipment {shipment.name} marked as delivered")
        
        return True
    
    def action_cancel(self):
        """Cancel shipment"""
        # Cancel active allocations
        self.allocation_ids.filtered(
            lambda a: a.state == 'active'
        ).action_cancel()
        self.write({'state': 'cancelled'})
        return True
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_view_deals(self):
        """View allocated deals"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Allocated Deals'),
            'res_model': 'dm.deal',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.deal_ids.ids)],
            'context': self.env.context,
        }