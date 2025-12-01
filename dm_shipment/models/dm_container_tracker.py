# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class DmContainerTracker(models.Model):
    """Container Tracker - Tag Model
    
    GPS/IoT tracking devices for containers.
    """
    _name = 'dm.container.tracker'
    _description = 'Container Tracker'
    _order = 'name'
    
    name = fields.Char(
        string='Tracker ID',
        required=True,
        index=True
    )
    
    tracker_type = fields.Selection([
        ('gps', 'GPS Only'),
        ('temperature', 'Temperature Monitor'),
        ('humidity', 'Humidity Monitor'),
        ('multi', 'Multi-Sensor'),
        ('other', 'Other')
    ], string='Tracker Type',
        default='gps'
    )
    
    notes = fields.Text(
        string='Notes'
    )
    
    _sql_constraints = [
        ('tracker_id_unique', 'UNIQUE(name)', 'Tracker ID must be unique')
    ]
    
    @api.model
    def name_create(self, name):
        """Support tags widget - create tracker on-the-fly"""
        tracker = self.create({'name': name})
        return tracker.id, tracker.name