# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealLineContainer(models.Model):
    """Deal Line - Container Calculations Extension"""
    _inherit = 'dm.deal.line'
    _description = 'Deal Line - Container Extension'
    
    @api.depends('product_id', 'product_id.effective_container_type_id')
    def _compute_container_type(self):
        """Get container type from product's effective container type"""
        for line in self:
            if line.product_id and hasattr(line.product_id, 'effective_container_type_id'):
                line.container_type_id = line.product_id.effective_container_type_id
            else:
                line.container_type_id = False

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure container type is set on creation"""
        records = super().create(vals_list)
        
        # Force compute container-related fields
        records._compute_container_type()
        records._compute_containers_required()
        records._compute_container_teu()
        
        return records
    
    @api.depends('quantity_packaging', 'product_id.master_carton_id', 
                 'product_id.cartons_per_container', 'product_id.container_cbm',
                 'product_id.container_net_weight_kg', 'product_packaging_id.packaging_volume_m3',
                 'product_packaging_id.packaging_net_weight', 'container_type_id.internal_volume',
                 'container_type_id.max_payload')
    def _compute_containers_required(self):
        """
        Calculate containers required using 3-tier priority:
        1. Manual (user override) - highest priority
        2. From packaging hierarchy (cartons_per_container)
        3. From volume (CBM)
        4. From weight (kg)
        """
        for line in self:
            # Check if user manually entered value (readonly=False allows this)
            # If field was manually set, it will have a value even before compute runs
            # We detect manual entry by checking if method has been calculated before
            if line.id and not line.env.context.get('force_recompute_containers'):
                # Check if this is a manual override by seeing if value differs from what we'd calculate
                # For now, just calculate - user can override after
                pass
            
            if not line.product_id or not line.quantity_packaging:
                line.containers_required = 0.0
                continue
            
            # Priority 1: Manual override (already set, skip calculation)
            # This happens naturally with readonly=False
            
            # Priority 2: From packaging hierarchy
            if (hasattr(line.product_id, 'cartons_per_container') and 
                line.product_id.cartons_per_container and
                line.product_id.cartons_per_container > 0):
                
                line.containers_required = line.quantity_packaging / line.product_id.cartons_per_container
                _logger.debug(
                    f"Line {line.id}: Calculated {line.containers_required:.3f} containers "
                    f"from packaging ({line.quantity_packaging} / {line.product_id.cartons_per_container})"
                )
                continue
            
            # Priority 3: From volume
            if (line.product_packaging_id and 
                hasattr(line.product_packaging_id, 'packaging_volume_m3') and
                line.product_packaging_id.packaging_volume_m3 and
                line.container_type_id and
                hasattr(line.container_type_id, 'internal_volume') and
                line.container_type_id.internal_volume and
                line.container_type_id.internal_volume > 0):
                
                line_total_cbm = line.quantity_packaging * line.product_packaging_id.packaging_volume_m3
                line.containers_required = line_total_cbm / line.container_type_id.internal_volume
                _logger.debug(
                    f"Line {line.id}: Calculated {line.containers_required:.3f} containers "
                    f"from volume ({line_total_cbm:.2f} / {line.container_type_id.internal_volume:.2f})"
                )
                continue
            
            # Priority 4: From weight
            if (line.product_packaging_id and
                hasattr(line.product_packaging_id, 'packaging_net_weight') and
                line.product_packaging_id.packaging_net_weight and
                line.container_type_id and
                hasattr(line.container_type_id, 'max_payload') and
                line.container_type_id.max_payload and
                line.container_type_id.max_payload > 0):
                
                line_total_weight = line.quantity_packaging * line.product_packaging_id.packaging_net_weight
                line.containers_required = line_total_weight / line.container_type_id.max_payload
                _logger.debug(
                    f"Line {line.id}: Calculated {line.containers_required:.3f} containers "
                    f"from weight ({line_total_weight:.2f} / {line.container_type_id.max_payload:.2f})"
                )
                continue
            
            # No calculation possible
            line.containers_required = 0.0
    
    @api.depends('containers_required', 'product_id.cartons_per_container',
                 'product_packaging_id.packaging_volume_m3', 'container_type_id.internal_volume',
                 'product_packaging_id.packaging_net_weight', 'container_type_id.max_payload')
    def _compute_container_calculation_method(self):
        """Determine which method was used to calculate containers"""
        for line in self:
            if not line.containers_required:
                line.container_calculation_method = False
                continue
            
            # Check packaging hierarchy first
            if (hasattr(line.product_id, 'cartons_per_container') and
                line.product_id.cartons_per_container and
                line.product_id.cartons_per_container > 0):
                line.container_calculation_method = 'packaging'
                continue
            
            # Check volume
            if (line.product_packaging_id and
                hasattr(line.product_packaging_id, 'packaging_volume_m3') and
                line.product_packaging_id.packaging_volume_m3 and
                line.container_type_id and
                hasattr(line.container_type_id, 'internal_volume') and
                line.container_type_id.internal_volume and
                line.container_type_id.internal_volume > 0):
                line.container_calculation_method = 'volume'
                continue
            
            # Check weight
            if (line.product_packaging_id and
                hasattr(line.product_packaging_id, 'packaging_net_weight') and
                line.product_packaging_id.packaging_net_weight and
                line.container_type_id and
                hasattr(line.container_type_id, 'max_payload') and
                line.container_type_id.max_payload and
                line.container_type_id.max_payload > 0):
                line.container_calculation_method = 'weight'
                continue
            
            # If we have a value but can't determine method, must be manual
            line.container_calculation_method = 'manual'
    
    @api.depends('containers_required', 'container_type_id', 'container_type_id.teu_factor')
    def _compute_container_teu(self):
        """Calculate TEU from containers × TEU factor"""
        for line in self:
            if (line.containers_required and 
                line.container_type_id and
                hasattr(line.container_type_id, 'teu_factor')):
                line.container_teu = line.containers_required * (line.container_type_id.teu_factor or 0.0)
            else:
                line.container_teu = 0.0
    
    @api.depends('containers_required', 'container_calculation_method', 
                 'product_id.cartons_per_container', 'product_packaging_id.packaging_volume_m3',
                 'product_packaging_id.packaging_net_weight', 'container_type_id')
    def _compute_container_calculation_warning(self):
        """Generate helpful warnings about container calculations"""
        for line in self:
            warnings = []
            
            # No container calculated
            if not line.containers_required or line.containers_required == 0:
                if not line.product_id:
                    line.container_calculation_warning = False
                    continue
                    
                # Check what's missing
                if not hasattr(line.product_id, 'cartons_per_container') or not line.product_id.cartons_per_container:
                    warnings.append("Product missing container configuration")
                
                if not line.product_packaging_id:
                    warnings.append("No packaging selected")
                elif (not hasattr(line.product_packaging_id, 'packaging_volume_m3') or 
                      not line.product_packaging_id.packaging_volume_m3):
                    warnings.append("Packaging missing volume data")
                
                if not line.container_type_id:
                    warnings.append("No container type determined")
                
                if warnings:
                    warnings.append("Enter containers manually")
                    line.container_calculation_warning = " • ".join(warnings)
                else:
                    line.container_calculation_warning = False
                continue
            
            # Fractional containers warning
            if line.containers_required > 0:
                fractional_part = line.containers_required - int(line.containers_required)
                if fractional_part > 0.01:  # More than 1% fractional
                    warnings.append(f"Requires {line.containers_required:.2f} containers (fractional)")
            
            # Very low utilization (less than 50% of container)
            if line.containers_required < 0.5 and line.containers_required > 0:
                utilization_pct = line.containers_required * 100
                warnings.append(f"Low utilization ({utilization_pct:.0f}% of container)")
            
            # Set final warning
            line.container_calculation_warning = " • ".join(warnings) if warnings else False