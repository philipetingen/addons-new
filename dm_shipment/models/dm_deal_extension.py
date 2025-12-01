# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealSubdealShipmentExtension(models.Model):
    """Extend dm.deal.subdeal with shipment allocation tracking
    
    This is the PRIMARY location for shipment allocation.
    Deal-level fields are computed from subdeal for backward compatibility.
    """
    _inherit = 'dm.deal.subdeal'

    # =========================================================================
    # SHIPMENT ALLOCATION (Primary - owned by subdeal)
    # =========================================================================
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        readonly=True,
        index=True,
        help='Shipment this subdeal is allocated to'
    )
    
    shipment_allocated = fields.Boolean(
        string='Allocated to Shipment',
        default=False,
        readonly=True,
        index=True,
        help='True if subdeal is allocated to a shipment'
    )
    
    # =========================================================================
    # MILESTONE LOCKING (Sprint C)
    # =========================================================================
    
    milestones_locked = fields.Boolean(
        string='Milestones Locked',
        compute='_compute_milestones_locked',
        store=True,
        help='True if allocated to shipment (milestones 3-6 controlled by shipment)'
    )
    
    @api.depends('shipment_allocated')
    def _compute_milestones_locked(self):
        """Lock shipment-related milestones when allocated"""
        for subdeal in self:
            subdeal.milestones_locked = subdeal.shipment_allocated
    
    # =========================================================================
    # CASCADE: SHIPMENT → SUBDEAL → DEAL (Sprint E)
    # =========================================================================
    
    def write(self, vals):
        """Extend write to cascade CURRENT milestones from shipment to deal"""
        res = super().write(vals)
        
        # Skip if not coming from shipment cascade
        if not self.env.context.get('from_shipment_cascade'):
            return res
        
        # Current milestone fields that cascade from shipment → subdeal → deal
        CURRENT_CASCADE_FIELDS = [
            'loading_current',
            'etd_current',
            'eta_current',
            'delivery_current',
        ]
        
        # Actual milestone fields (shipment overwrites)
        ACTUAL_CASCADE_FIELDS = [
            'loading_actual',
            'etd_actual',
            'eta_actual',
            'delivery_actual',
        ]
        
        # Build cascade vals
        cascade_vals = {}
        for field in CURRENT_CASCADE_FIELDS + ACTUAL_CASCADE_FIELDS:
            if field in vals:
                cascade_vals[field] = vals[field]
        
        if cascade_vals:
            for subdeal in self:
                if not subdeal.deal_id:
                    continue
                
                # Only cascade if this is the primary subdeal
                if subdeal.deal_id.primary_subdeal_id.id != subdeal.id:
                    _logger.debug(
                        f"Subdeal {subdeal.id}: Skipping cascade (not primary subdeal)"
                    )
                    continue
                
                # Cascade to deal (overwrite - shipment is source of truth)
                subdeal.deal_id.with_context(
                    from_subdeal_cascade=True,
                    skip_milestone_warnings=True
                ).write(cascade_vals)
                
                _logger.info(
                    f"Subdeal {subdeal.name}: Cascaded shipment milestones to deal "
                    f"{subdeal.deal_id.name}: {list(cascade_vals.keys())}"
                )
        
        return res


class DmDealShipmentExtension(models.Model):
    """Extend dm.deal with shipment allocation tracking (computed from subdeals)"""
    _inherit = 'dm.deal'
    
    # =========================================================================
    # ALLOCATION TRACKING (Computed from subdeals for backward compatibility)
    # =========================================================================
    
    shipment_allocated = fields.Boolean(
        string='Allocated to Shipment',
        compute='_compute_shipment_allocated',
        store=True,
        readonly=True,
        index=True,
        help='True if primary subdeal is allocated to a shipment'
    )
    
    shipment_ids = fields.Many2many(
        'dm.shipment',
        string='Shipments',
        compute='_compute_shipment_ids',
        help='Shipments containing this deal (via subdeals)'
    )
    
    shipment_count = fields.Integer(
        string='# Shipments',
        compute='_compute_shipment_ids'
    )
    
    # =========================================================================
    # MILESTONE LOCKING (Sprint C)
    # =========================================================================
    
    milestones_locked = fields.Boolean(
        string='Milestones Locked',
        compute='_compute_milestones_locked',
        store=True,
        help='True if allocated to shipment (milestones 3-6 controlled by shipment)'
    )
    
    @api.depends('shipment_allocated')
    def _compute_milestones_locked(self):
        """Lock shipment-related milestones when allocated"""
        for deal in self:
            deal.milestones_locked = deal.shipment_allocated
    
    # =========================================================================
    # COMPUTED METHODS
    # =========================================================================
    
    @api.depends('primary_subdeal_id', 'primary_subdeal_id.shipment_allocated')
    def _compute_shipment_allocated(self):
        """Compute from primary subdeal's allocation status"""
        for deal in self:
            if deal.primary_subdeal_id:
                deal.shipment_allocated = deal.primary_subdeal_id.shipment_allocated
            else:
                deal.shipment_allocated = False
    
    @api.depends('subdeal_ids', 'subdeal_ids.shipment_id')
    def _compute_shipment_ids(self):
        """Find shipments containing this deal's subdeals"""
        for deal in self:
            shipments = deal.subdeal_ids.mapped('shipment_id')
            deal.shipment_ids = shipments
            deal.shipment_count = len(shipments)
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def action_allocate_to_shipment(self):
        """Open wizard to allocate deal(s) to shipment"""
        deals = self.env.context.get('active_ids', [])
        if not deals:
            deals = [self.id]
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Allocate to Shipment'),
            'res_model': 'shipment.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_ids': deals,
                'active_model': 'dm.deal',
            }
        }
    
    def action_view_shipments(self):
        """View shipments containing this deal"""
        self.ensure_one()
        
        return {
            'name': _('Shipments: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'dm.shipment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.shipment_ids.ids)],
        }