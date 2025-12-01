# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class DmContainer(models.Model):
    """Container - Sprint 2
    
    Physical container unit with content tracking and utilization.
    Aggregates metrics from deal lines rather than recalculating.
    """
    _name = 'dm.container'
    _description = 'Container'
    _inherit = ['mail.thread']
    _order = 'shipment_id, sequence, id'
    
    # =========================================================================
    # HEADER
    # =========================================================================
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    # =========================================================================
    # CONTAINER TYPE
    # =========================================================================
    
    container_type_id = fields.Many2one(
        'dm.container.type',
        string='Container Type',
        required=True,
        tracking=True
    )
    
    container_number = fields.Char(
        string='Container #',
        tracking=True,
        help='ISO 6346 format: 4 letters + 7 digits'
    )
    
    is_reefer = fields.Boolean(
        related='container_type_id.is_reefer',
        string='Reefer Container',
        store=True
    )
    
    # =========================================================================
    # SECURITY
    # =========================================================================
    
    seal_tags = fields.Many2many(
        'dm.container.seal',
        string='Seals',
        help='Security seals applied to container'
    )
    
    tracker_tags = fields.Many2many(
        'dm.container.tracker',
        string='Trackers',
        help='GPS/temperature tracking devices'
    )
    
    is_smart_container = fields.Boolean(
        string='Smart Container',
        help='Has IoT tracking capabilities'
    )
    
    # =========================================================================
    # REEFER SETTINGS
    # =========================================================================
    
    temp_required = fields.Float(
        string='Required Temp (°C)',
        digits=(5, 1),
        help='Target temperature for reefer container'
    )
    
    temp_range_min = fields.Float(
        string='Min Temp (°C)',
        digits=(5, 1)
    )
    
    temp_range_max = fields.Float(
        string='Max Temp (°C)',
        digits=(5, 1)
    )
    
    humidity_required = fields.Float(
        string='Required Humidity (%)',
        digits=(5, 1)
    )
    
    humidity_range_min = fields.Float(
        string='Min Humidity (%)',
        digits=(5, 1)
    )
    
    humidity_range_max = fields.Float(
        string='Max Humidity (%)',
        digits=(5, 1)
    )
    
    # =========================================================================
    # CONTENT
    # =========================================================================
    
    line_ids = fields.One2many(
        'dm.container.line',
        'container_id',
        string='Container Lines'
    )
    
    # =========================================================================
    # UTILIZATION (AGGREGATED FROM DEAL LINES)
    # =========================================================================
    
    planned_packages = fields.Float(
        string='Planned Packages',
        compute='_compute_utilization',
        store=True,
        digits=(16, 3),
        help='Sum of planned packages from container lines'
    )
    
    actual_packages = fields.Float(
        string='Actual Packages',
        compute='_compute_utilization',
        store=True,
        digits=(16, 3),
        help='Sum of actual loaded packages'
    )
    
    planned_weight = fields.Float(
        string='Planned Weight (kg)',
        compute='_compute_utilization',
        store=True,
        digits=(16, 2),
        help='Aggregated from deal line weights'
    )
    
    actual_weight = fields.Float(
        string='Actual Weight (kg)',
        compute='_compute_utilization',
        store=True,
        digits=(16, 2),
        help='Actual weight based on loaded quantities'
    )
    
    planned_volume = fields.Float(
        string='Planned Volume (cbm)',
        compute='_compute_utilization',
        store=True,
        digits=(16, 3),
        help='Estimated volume (if available from packaging)'
    )
    
    actual_volume = fields.Float(
        string='Actual Volume (cbm)',
        compute='_compute_utilization',
        store=True,
        digits=(16, 3),
        help='Actual volume based on loaded quantities'
    )
    
    utilization_weight = fields.Float(
        string='Weight Utilization (%)',
        compute='_compute_utilization',
        store=True,
        digits=(5, 1)
    )
    
    utilization_volume = fields.Float(
        string='Volume Utilization (%)',
        compute='_compute_utilization',
        store=True,
        digits=(5, 1)
    )
    
    is_over_capacity = fields.Boolean(
        string='Over Capacity',
        compute='_compute_utilization',
        store=True,
        help='Weight or volume exceeds container limits'
    )
    
    container_teu = fields.Float(
        string='TEU',
        related='container_type_id.teu_factor',
        store=True,
        digits=(16, 2),
        help='Twenty-foot Equivalent Units'
    )
    
    # =========================================================================
    # VGM
    # =========================================================================
    
    vgm = fields.Float(
        string='VGM (kg)',
        digits=(16, 2),
        tracking=True,
        help='Verified Gross Mass'
    )
    
    vgm_declaration_date = fields.Date(
        string='VGM Declaration Date',
        tracking=True
    )
    
    # =========================================================================
    # STATE
    # =========================================================================
    
    state = fields.Selection(
        related='shipment_id.state',
        string='Status',
        store=True
    )
    
    # =========================================================================
    # COMPUTED METHODS
    # =========================================================================
    
    @api.depends('line_ids', 'line_ids.quantity_planned', 'line_ids.quantity_loaded',
                 'line_ids.deal_line_id', 'line_ids.deal_line_id.weight',
                 'container_type_id.max_payload', 'container_type_id.internal_volume')
    def _compute_utilization(self):
        """
        Aggregate utilization from container lines and deal lines.
        Uses existing deal line computations instead of recalculating.
        """
        for container in self:
            # Package counts (from container lines directly)
            container.planned_packages = sum(container.line_ids.mapped('quantity_planned'))
            container.actual_packages = sum(container.line_ids.mapped('quantity_loaded'))
            
            # Weight aggregation from deal lines
            planned_weight = 0.0
            actual_weight = 0.0
            
            for line in container.line_ids:
                deal_line = line.deal_line_id
                
                # Weight from deal line (already computed there)
                if deal_line and deal_line.weight:
                    # Deal line weight is for quantity_packaging
                    # Scale proportionally for container line quantity
                    if deal_line.quantity_packaging > 0:
                        weight_per_pkg = deal_line.weight / deal_line.quantity_packaging
                        planned_weight += line.quantity_planned * weight_per_pkg
                        actual_weight += line.quantity_loaded * weight_per_pkg
            
            container.planned_weight = planned_weight
            container.actual_weight = actual_weight
            
            # Volume estimation (best effort - may not always be available)
            planned_volume = 0.0
            actual_volume = 0.0
            
            for line in container.line_ids:
                # Try to get volume from product.template master carton
                product_tmpl = line.product_id.product_tmpl_id
                
                # Check if master carton has volume
                if hasattr(product_tmpl, 'master_carton_id') and product_tmpl.master_carton_id:
                    master_carton = product_tmpl.master_carton_id
                    if hasattr(master_carton, 'packaging_volume_m3'):
                        pkg_volume = master_carton.packaging_volume_m3 or 0.0
                        planned_volume += line.quantity_planned * pkg_volume
                        actual_volume += line.quantity_loaded * pkg_volume
            
            container.planned_volume = planned_volume
            container.actual_volume = actual_volume
            
            # Utilization percentages
            if container.container_type_id:
                max_payload = container.container_type_id.max_payload or 0.0
                max_volume = container.container_type_id.internal_volume or 0.0
                
                if max_payload > 0:
                    container.utilization_weight = (planned_weight / max_payload) * 100
                else:
                    container.utilization_weight = 0.0
                
                if max_volume > 0:
                    container.utilization_volume = (planned_volume / max_volume) * 100
                else:
                    container.utilization_volume = 0.0
                
                # Over capacity check
                container.is_over_capacity = (
                    (max_payload > 0 and planned_weight > max_payload) or
                    (max_volume > 0 and planned_volume > max_volume)
                )
            else:
                container.utilization_weight = 0.0
                container.utilization_volume = 0.0
                container.is_over_capacity = False
    
    # =========================================================================
    # CONSTRAINTS
    # =========================================================================
    
    @api.constrains('container_number')
    def _check_container_number(self):
        """Validate ISO 6346 format (if provided)"""
        for container in self:
            if container.container_number:
                # ISO 6346: 4 letters + 7 digits
                pattern = r'^[A-Z]{4}\d{7}$'
                if not re.match(pattern, container.container_number.upper()):
                    raise ValidationError(_(
                        'Container number must follow ISO 6346 format: '
                        '4 letters + 7 digits (e.g. ABCD1234567)'
                    ))
    
    # =========================================================================
    # DISPLAY
    # =========================================================================
    
    def name_get(self):
        result = []
        for container in self:
            if container.container_number:
                name = container.container_number
            else:
                name = f"Container #{container.sequence}"
            
            if container.container_type_id:
                name += f" ({container.container_type_id.name})"
            
            result.append((container.id, name))
        return result