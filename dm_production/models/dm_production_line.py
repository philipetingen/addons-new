# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmProductionLine(models.Model):
    _name = 'dm.production.line'
    _description = 'Production Run Line'
    _order = 'production_run_id, sequence, id'
    
    # ========================================================================
    # HEADER
    # ========================================================================
    
    production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    state = fields.Selection(
        related='production_run_id.state',
        string='PR State',
        store=True,
        readonly=True
    )
    
    # ========================================================================
    # SOURCE
    # ========================================================================
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        ondelete='restrict',
        index=True
    )
    
    deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        required=True,
        ondelete='restrict',
        index=True,
        help='Source deal line for this production line'
    )
    
    # ========================================================================
    # PRODUCT & PACKAGING
    # ========================================================================
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        readonly=True,
        help='Denormalized from deal line'
    )
    
    product_name = fields.Char(
        related='product_id.name',
        string='Product Name',
        readonly=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Package Type',
        required=True,
        readonly=True,
        help='Denormalized from deal line'
    )
    
    packaging_name = fields.Char(
        related='product_packaging_id.name',
        string='Package',
        readonly=True
    )
    
    packaging_qty = fields.Float(
        related='product_packaging_id.qty',
        string='Units/Package',
        readonly=True
    )
    
    # ========================================================================
    # QUANTITIES (PACKAGE-NATIVE)
    # ========================================================================
    
    quantity_ordered = fields.Float(
        string='Ordered (Pkg)',
        digits='Product Unit of Measure',
        required=True,
        readonly=True,
        help='Ordered quantity from deal line (packages)'
    )
    
    quantity_produced = fields.Float(
        string='Produced (Pkg)',
        digits='Product Unit of Measure',
        default=0.0,
        help='Actually produced quantity (packages)'
    )
        
    quantity_variance = fields.Float(
        string='Variance (Pkg)',
        compute='_compute_variance',
        store=True,
        digits='Product Unit of Measure',
        help='Produced - Ordered (negative = shortage)'
    )
    
    variance_percent = fields.Float(
        string='Variance %',
        compute='_compute_variance',
        store=True,
        digits=(16, 2),
        help='Variance as percentage of ordered'
    )
    
    # Unit quantities (reference only)
    quantity_ordered_units = fields.Float(
        string='Ordered (Units)',
        compute='_compute_unit_quantities',
        store=True,
        digits='Product Unit of Measure',
        help='Ordered quantity in units (reference only)'
    )
    
    quantity_produced_units = fields.Float(
        string='Produced (Units)',
        compute='_compute_unit_quantities',
        store=True,
        digits='Product Unit of Measure',
        help='Produced quantity in units (reference only)'
    )
    
    # ========================================================================
    # CONTAINER & TEU (COMPUTED FROM DEAL LINE PATTERN)
    # ========================================================================
    
    container_type_id = fields.Many2one(
        'dm.container.type',
        string='Container Type',
        compute='_compute_container_info',
        store=True,
        help='Container type from product'
    )
    
    containers_ordered = fields.Float(
        string='Containers Ordered',
        compute='_compute_container_info',
        store=True,
        digits=(16, 3),
        help='Containers for ordered quantity'
    )
    
    containers_produced = fields.Float(
        string='Containers Produced',
        compute='_compute_container_info',
        store=True,
        digits=(16, 3),
        help='Containers for produced quantity'
    )
    
    teu_ordered = fields.Float(
        string='TEU Ordered',
        compute='_compute_container_info',
        store=True,
        digits=(16, 2),
        help='TEU for ordered quantity'
    )
    
    teu_produced = fields.Float(
        string='TEU Produced',
        compute='_compute_container_info',
        store=True,
        digits=(16, 2),
        help='TEU for produced quantity'
    )
    
    # ========================================================================
    # NOTES
    # ========================================================================
    
    notes = fields.Text(
        string='Production Notes',
        help='Notes about production of this line'
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('quantity_ordered', 'quantity_produced')
    def _compute_variance(self):
        """Calculate quantity variance"""
        for line in self:
            line.quantity_variance = line.quantity_produced - line.quantity_ordered
            
            if line.quantity_ordered:
                line.variance_percent = (line.quantity_variance / line.quantity_ordered) * 100
            else:
                line.variance_percent = 0.0
    
    @api.depends('quantity_ordered', 'quantity_produced', 'packaging_qty')
    def _compute_unit_quantities(self):
        """Convert package quantities to units (reference only)"""
        for line in self:
            line.quantity_ordered_units = line.quantity_ordered * line.packaging_qty
            line.quantity_produced_units = line.quantity_produced * line.packaging_qty
    
    @api.depends('product_id', 'product_packaging_id', 'quantity_ordered', 'quantity_produced',
                 'product_id.effective_container_type_id')
    def _compute_container_info(self):
        """
        Calculate containers and TEU using same logic as dm.deal.line
        Mimics the 3-tier priority system
        """
        for line in self:
            # Get container type from product
            if line.product_id and hasattr(line.product_id, 'effective_container_type_id'):
                line.container_type_id = line.product_id.effective_container_type_id
            else:
                line.container_type_id = False
            
            # Calculate containers for ordered quantity
            line.containers_ordered = line._calculate_containers(line.quantity_ordered)
            
            # Calculate containers for produced quantity
            line.containers_produced = line._calculate_containers(line.quantity_produced)
            
            # Calculate TEU
            if line.container_type_id and hasattr(line.container_type_id, 'teu_factor'):
                teu_factor = line.container_type_id.teu_factor or 0.0
                line.teu_ordered = line.containers_ordered * teu_factor
                line.teu_produced = line.containers_produced * teu_factor
            else:
                line.teu_ordered = 0.0
                line.teu_produced = 0.0
    
    def _calculate_containers(self, quantity_packages):
        """
        Calculate containers for given quantity using 3-tier priority:
        1. From packaging hierarchy (cartons_per_container)
        2. From volume (CBM)
        3. From weight (kg)
        
        Mirrors logic from dm.deal.line._compute_containers_required
        """
        self.ensure_one()
        
        if not quantity_packages or quantity_packages == 0:
            return 0.0
        
        # Priority 1: From packaging hierarchy
        if (hasattr(self.product_id, 'cartons_per_container') and 
            self.product_id.cartons_per_container and
            self.product_id.cartons_per_container > 0):
            return quantity_packages / self.product_id.cartons_per_container
        
        # Priority 2: From volume
        if (self.product_packaging_id and 
            hasattr(self.product_packaging_id, 'packaging_volume_m3') and
            self.product_packaging_id.packaging_volume_m3 and
            self.container_type_id and
            hasattr(self.container_type_id, 'internal_volume') and
            self.container_type_id.internal_volume and
            self.container_type_id.internal_volume > 0):
            
            total_cbm = quantity_packages * self.product_packaging_id.packaging_volume_m3
            return total_cbm / self.container_type_id.internal_volume
        
        # Priority 3: From weight
        if (self.product_packaging_id and
            hasattr(self.product_packaging_id, 'packaging_net_weight') and
            self.product_packaging_id.packaging_net_weight and
            self.container_type_id and
            hasattr(self.container_type_id, 'max_payload') and
            self.container_type_id.max_payload and
            self.container_type_id.max_payload > 0):
            
            total_weight = quantity_packages * self.product_packaging_id.packaging_net_weight
            return total_weight / self.container_type_id.max_payload
        
        # No calculation possible
        return 0.0
    
    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    
    @api.constrains('quantity_produced')
    def _check_quantity_produced(self):
        """Cannot have negative produced quantity"""
        for line in self:
            if line.quantity_produced < 0:
                raise ValidationError(_(
                    'Produced quantity cannot be negative for line %s'
                ) % line.product_name)
    
    @api.constrains('deal_line_id', 'production_run_id')
    def _check_unique_deal_line(self):
        """Each deal line can only appear once per production run"""
        for line in self:
            duplicate = self.search([
                ('id', '!=', line.id),
                ('production_run_id', '=', line.production_run_id.id),
                ('deal_line_id', '=', line.deal_line_id.id)
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'Deal line %s already exists in production run %s'
                ) % (line.deal_line_id.product_id.name, line.production_run_id.name))
    
    _sql_constraints = [
        ('deal_line_pr_uniq',
         'UNIQUE(production_run_id, deal_line_id)',
         'Deal line must be unique per production run'),
    ]
    
    # ========================================================================
    # DISPLAY
    # ========================================================================
    
    def name_get(self):
        result = []
        for line in self:
            name = f"{line.production_run_id.name} - {line.product_name}"
            result.append((line.id, name))
        return result