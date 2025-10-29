# -*- coding: utf-8 -*-
"""
State Machine Implementation for dm.deal
Add this to your CORE dm_deal/models/dm_deal.py file
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmDeal(models.Model):
    _inherit = 'dm.deal'
    
    # =======================================================================
    # STATE FIELD UPDATE
    # =======================================================================
    # UPDATE your existing state field to include 'completed':
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('confirmed', 'Confirmed'),
        ('partial', 'Partial Allocation'),
        ('allocated', 'Allocated'),
        ('ready', 'Ready to Ship'),
        ('shipping', 'Shipping'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),  # ✨ NEW - Manual closure
        ('cancelled', 'Cancelled')
    ], default='draft', tracking=True, string='Status')
    
    # =======================================================================
    # STATE COMPUTATION METHOD
    # =======================================================================
    
    def _compute_deal_state_from_allocations(self):
        """
        Compute deal state based on allocation progress.
        
        State Priority Hierarchy:
        1. delivered (shipment delivered) - AUTO
        2. shipping (shipment shipped/arrived) - AUTO
        3. ready (production ready, shipment < shipped) - AUTO
        4. allocated (has PR + Ship) - AUTO
        5. partial (has PR OR Ship) - AUTO
        6. confirmed (SO/PO confirmed) - AUTO
        7. validated (SO/PO exists) - AUTO
        8. draft (initial) - AUTO
        
        Does NOT override: completed, cancelled (manual states)
        """
        for deal in self:
            # Skip manually set final states
            if deal.state in ['completed', 'cancelled']:
                _logger.debug(
                    f"Skipping state computation for {deal.name} - "
                    f"in final state '{deal.state}'"
                )
                continue
            
            # Get active/completed allocations
            pr_allocs = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'production' 
                and a.state in ['active', 'completed']
            )
            ship_allocs = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'shipment' 
                and a.state in ['active', 'completed']
            )
            
            old_state = deal.state
            new_state = old_state
            
            # Priority 1: Shipment delivered → delivered
            if ship_allocs:
                delivered_ships = [
                    a for a in ship_allocs 
                    if a.shipment_id and a.shipment_id.state == 'delivered'
                ]
                if delivered_ships:
                    new_state = 'delivered'
                    if old_state != new_state:
                        deal.state = new_state
                        _logger.info(
                            f"Deal {deal.name}: {old_state} → {new_state} "
                            f"(shipment delivered)"
                        )
                    continue
            
            # Priority 2: Shipment in progress → shipping
            if ship_allocs:
                shipping_states = [
                    a for a in ship_allocs 
                    if a.shipment_id and a.shipment_id.state in ['shipped', 'arrived']
                ]
                if shipping_states:
                    new_state = 'shipping'
                    if old_state != new_state:
                        deal.state = new_state
                        _logger.info(
                            f"Deal {deal.name}: {old_state} → {new_state} "
                            f"(shipment in progress)"
                        )
                    continue
            
            # Priority 3: Production ready, shipment not yet shipped → ready
            if pr_allocs:
                ready_prs = [
                    a for a in pr_allocs
                    if a.production_run_id 
                    and a.production_run_id.state in ['ready', 'done']
                ]
                
                if ready_prs and len(ready_prs) == len(pr_allocs):
                    # All PRs are ready
                    if ship_allocs:
                        # Has shipment - check if not yet shipped
                        not_shipped = all(
                            a.shipment_id.state in ['draft', 'confirmed', 'loading']
                            for a in ship_allocs if a.shipment_id
                        )
                        if not_shipped:
                            new_state = 'ready'
                            if old_state != new_state:
                                deal.state = new_state
                                _logger.info(
                                    f"Deal {deal.name}: {old_state} → {new_state} "
                                    f"(production ready, shipment not yet shipped)"
                                )
                            continue
                    else:
                        # No shipment yet
                        new_state = 'ready'
                        if old_state != new_state:
                            deal.state = new_state
                            _logger.info(
                                f"Deal {deal.name}: {old_state} → {new_state} "
                                f"(production ready, no shipment)"
                            )
                        continue
            
            # Priority 4: Has both allocations → allocated
            if pr_allocs and ship_allocs:
                new_state = 'allocated'
                if old_state != new_state:
                    deal.state = new_state
                    _logger.info(
                        f"Deal {deal.name}: {old_state} → {new_state} "
                        f"(has production + shipment)"
                    )
                continue
            
            # Priority 5: Has one allocation → partial
            if pr_allocs or ship_allocs:
                new_state = 'partial'
                if old_state != new_state:
                    deal.state = new_state
                    alloc_type = 'production' if pr_allocs else 'shipment'
                    _logger.info(
                        f"Deal {deal.name}: {old_state} → {new_state} "
                        f"(has {alloc_type} only)"
                    )
                continue
            
            # Priority 6: SO+PO confirmed → confirmed
            if hasattr(deal, 'so_confirmed') and hasattr(deal, 'po_confirmed'):
                if deal.so_confirmed and deal.po_confirmed:
                    new_state = 'confirmed'
                    if old_state != new_state:
                        deal.state = new_state
                        _logger.info(
                            f"Deal {deal.name}: {old_state} → {new_state} "
                            f"(SO+PO confirmed)"
                        )
                    continue
            
            # Priority 7: Has SO or PO → validated
            if hasattr(deal, 'sale_order_ids') and hasattr(deal, 'purchase_order_ids'):
                if deal.sale_order_ids or deal.purchase_order_ids:
                    new_state = 'validated'
                    if old_state != new_state:
                        deal.state = new_state
                        _logger.info(
                            f"Deal {deal.name}: {old_state} → {new_state} "
                            f"(has SO/PO)"
                        )
                    continue
            
            # Priority 8: Default → draft
            if old_state not in ['draft', 'validated', 'confirmed']:
                new_state = 'draft'
                if old_state != new_state:
                    deal.state = new_state
                    _logger.info(
                        f"Deal {deal.name}: {old_state} → {new_state} "
                        f"(no allocations or SO/PO)"
                    )
    
    # =======================================================================
    # ACTION METHODS
    # =======================================================================
    
    def action_complete(self):
        """
        Mark deal as completed (manual closure by manager).
        
        Can only be done from 'delivered' state.
        Validates that all follow-up activities are closed.
        """
        for deal in self:
            # Validation: Must be delivered
            if deal.state != 'delivered':
                raise UserError(_(
                    'Only delivered deals can be marked as completed.\n\n'
                    'Current state: %s\n'
                    'Please ensure the shipment is delivered first.'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            # Optional: Check for outstanding downpayments
            if hasattr(deal, 'downpayment_request_ids'):
                outstanding_dps = deal.downpayment_request_ids.filtered(
                    lambda dp: dp.state not in ['paid', 'cancelled']
                )
                if outstanding_dps:
                    raise UserError(_(
                        'Cannot complete deal with outstanding downpayment requests.\n\n'
                        'Outstanding requests: %s\n\n'
                        'Please settle or cancel them first.'
                    ) % ', '.join(outstanding_dps.mapped('name')))
            
            # Optional: Check for open activities
            if deal.activity_ids:
                raise UserError(_(
                    'Cannot complete deal with open activities.\n\n'
                    'Please close all activities first.'
                ))
            
            # Mark as completed
            deal.write({'state': 'completed'})
            
            # Log completion
            deal.message_post(
                body=_('Deal completed by %s') % self.env.user.name,
                subject=_('Deal Completed'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(
                f"Deal {deal.name} marked as completed by {self.env.user.name}"
            )
        
        return True
    
    def action_reopen(self):
        """
        Reopen a completed deal (back to delivered state).
        Manager action only.
        """
        for deal in self:
            if deal.state != 'completed':
                raise UserError(_(
                    'Only completed deals can be reopened.\n\n'
                    'Current state: %s'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            deal.write({'state': 'delivered'})
            
            deal.message_post(
                body=_('Deal reopened by %s') % self.env.user.name,
                subject=_('Deal Reopened'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(
                f"Deal {deal.name} reopened by {self.env.user.name}"
            )
        
        return True