# -*- coding: utf-8 -*-

from odoo import fields, models


class DmAllocation(models.Model):
    """
    Extend dm.allocation with production run reference
    """
    _inherit = 'dm.allocation'
    
    production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        ondelete='cascade',
        help='Production run for this allocation (when allocation_type=production)'
    )