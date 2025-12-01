# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmContainerLine(models.Model):
    """Container Line - Sprint 2
    
    Links deal line to container with planned/actual quantities.
    """
    _name = 'dm.container.line'
    _description = 'Container Line'
    _order = 'container_id, sequence, id'
    
    # =========================================================================
    # HEADER
    # =========================================================================
    
    container_id = fields.Many2one(
        'dm.container',
        string='Container',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        related='container_id.shipment_id',
        string='Shipment',
        store=True,
        index=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    # =========================================================================
    # SOURCE
    # =========================================================================
    
    deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        required=True,
        ondelete='restrict',
        index=True
    )
    
    deal_id = fields.Many2one(
        'dm.deal',
        related='deal_line_id.deal_id',
        string='Deal',
        store=True,
        index=True
    )
    
    # =========================================================================
    # PRODUCT INFO (RELATED)
    # =========================================================================
    
    product_id = fields.Many2one(
        'product.product',
        related='deal_line_id.product_id',
        string='Product',
        store=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        related='deal_line_id.product_packaging_id',
        string='Packaging',
        store=True
    )
    
    # =========================================================================
    # QUANTITIES (PACKAGE-NATIVE)
    # =========================================================================
    
    quantity_planned = fields.Float(
        string='Planned (Pkg)',
        required=True,
        digits=(16, 3),
        help='Planned quantity to load in this container'
    )
    
    quantity_loaded = fields.Float(
        string='Loaded (Pkg)',
        digits=(16, 3),
        help='Actual quantity loaded'
    )
    
    quantity_variance = fields.Float(
        string='Variance (Pkg)',
        compute='_compute_variance',
        store=True,
        digits=(16, 3),
        help='Difference: Loaded - Planned'
    )
    
    variance_percentage = fields.Float(
        string='Variance %',
        compute='_compute_variance',
        store=True,
        digits=(5, 2)
    )
    
    # =========================================================================
    # LOT TRACKING (Sprint 4)
    # =========================================================================
    
    lot_ids = fields.Many2many(
        'dm.deal.line.lot',
        string='Lots Loaded',
        help='Production lots loaded in this container for this deal line'
    )
    
    lot_count = fields.Integer(
        compute='_compute_lot_count',
        string='# Lots'
    )
    
    lot_summary = fields.Char(
        compute='_compute_lot_summary',
        string='Lot Summary'
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
    
    @api.depends('quantity_planned', 'quantity_loaded')
    def _compute_variance(self):
        """Calculate variance"""
        for line in self:
            line.quantity_variance = line.quantity_loaded - line.quantity_planned
            
            if line.quantity_planned > 0:
                line.variance_percentage = (line.quantity_variance / line.quantity_planned) * 100
            else:
                line.variance_percentage = 0.0
    
    @api.depends('lot_ids')
    def _compute_lot_count(self):
        """Count lots"""
        for line in self:
            line.lot_count = len(line.lot_ids)
    
    @api.depends('lot_ids', 'lot_ids.lot_number')
    def _compute_lot_summary(self):
        """Summary of lot numbers"""
        for line in self:
            if line.lot_ids:
                lot_numbers = line.lot_ids.mapped('lot_number')
                line.lot_summary = ', '.join(lot_numbers[:3])
                if len(lot_numbers) > 3:
                    line.lot_summary += f' (+{len(lot_numbers) - 3} more)'
            else:
                line.lot_summary = ''
    
    # =========================================================================
    # CONSTRAINTS
    # =========================================================================
    
    @api.constrains('quantity_planned')
    def _check_quantity_planned(self):
        """Planned quantity must be positive"""
        for line in self:
            if line.quantity_planned <= 0:
                raise ValidationError(_(
                    'Planned quantity must be positive. Got: %.3f'
                ) % line.quantity_planned)
    
    # =========================================================================
    # DISPLAY
    # =========================================================================
    
    def name_get(self):
        result = []
        for line in self:
            name = f"{line.product_id.name or 'Product'}"
            if line.product_packaging_id:
                name += f" ({line.product_packaging_id.name})"
            name += f" × {line.quantity_planned:.1f}"
            result.append((line.id, name))
        return result