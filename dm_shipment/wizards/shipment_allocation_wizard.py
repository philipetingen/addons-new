# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ShipmentAllocationWizard(models.TransientModel):
    """Shipment Allocation Wizard - BLACK BOX Implementation"""
    _name = 'dm.shipment.allocation.wizard'
    _description = 'Shipment Allocation Wizard'
    
    deal_ids = fields.Many2many('dm.deal', string='Deals', required=True)
    shipment_id = fields.Many2one('dm.shipment', string='Shipment',
                                   domain=[('state', 'in', ['draft', 'confirmed'])])
    create_new_shipment = fields.Boolean(string='Create New Shipment', default=True)
    loading_port_id = fields.Many2one('dm.port', string='Loading Port')
    discharge_port_id = fields.Many2one('dm.port', string='Discharge Port')
    etd = fields.Date(string='ETD')
    eta = fields.Date(string='ETA')
    
    @api.onchange('create_new_shipment')
    def _onchange_create_new_shipment(self):
        if self.create_new_shipment:
            self.shipment_id = False
        else:
            self.loading_port_id = False
            self.discharge_port_id = False
            self.etd = False
            self.eta = False
    
    @api.onchange('deal_ids')
    def _onchange_deal_ids(self):
        """Pre-fill fields from first deal"""
        if self.deal_ids and self.create_new_shipment:
            deal = self.deal_ids[0]
            
            # Pre-fill ports from deal
            if hasattr(deal, 'loading_port_id') and deal.loading_port_id:
                self.loading_port_id = deal.loading_port_id
            
            if hasattr(deal, 'discharge_port_id') and deal.discharge_port_id:
                self.discharge_port_id = deal.discharge_port_id
            
            # Pre-fill dates from deal
            if hasattr(deal, 'etd_current') and deal.etd_current:
                self.etd = deal.etd_current
            elif hasattr(deal, 'etd_requested') and deal.etd_requested:
                self.etd = deal.etd_requested
            
            if hasattr(deal, 'eta_current') and deal.eta_current:
                self.eta = deal.eta_current
            elif hasattr(deal, 'eta_requested') and deal.eta_requested:
                self.eta = deal.eta_requested
    
    def action_allocate(self):
        self.ensure_one()
        if self.create_new_shipment:
            if not self.loading_port_id or not self.discharge_port_id:
                raise UserError(_('Ports are required'))
            shipment = self.env['dm.shipment'].create({
                'loading_port_id': self.loading_port_id.id,
                'discharge_port_id': self.discharge_port_id.id,
                'etd': self.etd,
                'eta': self.eta,
            })
        else:
            shipment = self.shipment_id
        
        allocations_created = 0
        for deal in self.deal_ids:
            self.env['dm.allocation'].create({
                'deal_id': deal.id,
                'allocation_type': 'shipment',
                'shipment_id': shipment.id,
                'state': 'active',
            })
            allocations_created += 1
            
            # FIX #3: Update deal state ONLY if BOTH PR and Shipment allocated
            if deal.state == 'confirmed':
                # Check if production also allocated
                if deal.production_allocated:
                    deal.write({'state': 'allocated'})
                # If only shipment allocated, stay in 'confirmed'
        
        # FIX #5: Close wizard with success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d deal(s) allocated to shipment %s') % (
                    allocations_created, shipment.name
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }