# -*- coding: utf-8 -*-
from odoo import api, fields, models

class DmDealLineLotShipmentExtension(models.Model):
    """Extend deal line lot with container tracking"""
    _inherit = 'dm.deal.line.lot'
    
    container_line_ids = fields.Many2many(
        'dm.container.line',
        'dm_container_line_lot_rel',
        'lot_id',
        'container_line_id',
        string='Container Lines',
        help='Container lines this lot was loaded into'
    )
    
    container_count = fields.Integer(
        string='# Containers',
        compute='_compute_container_count'
    )
    
    @api.depends('container_line_ids')
    def _compute_container_count(self):
        for lot in self:
            lot.container_count = len(lot.container_line_ids)