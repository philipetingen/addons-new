# -*- coding: utf-8 -*-

from odoo import fields, models


class DmAllocation(models.Model):
    """
    Extend dm.allocation with shipment reference
    """
    _inherit = 'dm.allocation'
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        ondelete='cascade',
        help='Shipment for this allocation (when allocation_type=shipment)'
    )