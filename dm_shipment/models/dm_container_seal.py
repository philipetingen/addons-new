# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class DmContainerSeal(models.Model):
    """Container Seal - Tag Model
    
    Security seals for container tracking.
    """
    _name = 'dm.container.seal'
    _description = 'Container Seal'
    _order = 'name'
    
    name = fields.Char(
        string='Seal Number',
        required=True,
        index=True
    )
    
    seal_type = fields.Selection([
        ('bolt', 'Bolt Seal'),
        ('cable', 'Cable Seal'),
        ('plastic', 'Plastic Seal'),
        ('electronic', 'Electronic Seal'),
        ('other', 'Other')
    ], string='Seal Type',
        default='bolt'
    )
    
    notes = fields.Text(
        string='Notes'
    )
    
    _sql_constraints = [
        ('seal_number_unique', 'UNIQUE(name)', 'Seal number must be unique')
    ]
    
    @api.model
    def name_create(self, name):
        """Support tags widget - create seal on-the-fly"""
        seal = self.create({'name': name})
        return seal.id, seal.name