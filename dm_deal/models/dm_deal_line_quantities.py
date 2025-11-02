# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealLineQuantities(models.Model):
    """Deal Line - Quantities Extension"""
    _inherit = 'dm.deal.line'
    _description = 'Deal Line - Quantities Extension'
    
    # =========================================================================
    # THREE-QUANTITY SYSTEM (Phase 4B Step 2)
    # =========================================================================
    
    # Semantic alias for quantity_packaging (commercial intent)
    quantity_ordered = fields.Float(
        string='Quantity Ordered',
        compute='_compute_quantity_ordered',
        inverse='_inverse_quantity_ordered',
        store=True,
        digits=(16, 3),
        help="Commercial quantity - what customer ordered (in packages)"
    )
    
    # Unit conversions for produced/loaded quantities
    quantity_produced_units = fields.Float(
        string='Produced (Units)',
        compute='_compute_quantity_produced_units',
        store=True,
        digits=(16, 3),
        help="Produced quantity in product UOM"
    )
    
    quantity_loaded_units = fields.Float(
        string='Loaded (Units)',
        compute='_compute_quantity_loaded_units',
        store=True,
        digits=(16, 3),
        help="Loaded quantity in product UOM"
    )
    
    # Variance tracking
    quantity_variance_production = fields.Float(
        string='Production Variance',
        compute='_compute_quantity_variances',
        store=True,
        digits=(16, 3),
        help="Difference between ordered and produced"
    )
    
    quantity_variance_loading = fields.Float(
        string='Loading Variance',
        compute='_compute_quantity_variances',
        store=True,
        digits=(16, 3),
        help="Difference between produced and loaded"
    )
    
    quantity_variance_total = fields.Float(
        string='Total Variance',
        compute='_compute_quantity_variances',
        store=True,
        digits=(16, 3),
        help="Difference between ordered and loaded"
    )
    
    # Enhanced status indicators
    production_status = fields.Selection([
        ('pending', 'Pending Production'),
        ('in_progress', 'In Production'),
        ('completed', 'Production Complete'),
        ('variance', 'Quantity Variance')
    ], string='Production Status',
        compute='_compute_production_status',
        store=True
    )
    
    loading_status = fields.Selection([
        ('pending', 'Pending Loading'),
        ('loaded', 'Loaded'),
        ('variance', 'Loading Variance')
    ], string='Loading Status',
        compute='_compute_loading_status',
        store=True
    )
    
    # =========================================================================
    # COMPUTED METHODS - THREE-QUANTITY SYSTEM
    # =========================================================================
    
    @api.depends('quantity_packaging')
    def _compute_quantity_ordered(self):
        """Alias for quantity_packaging for semantic clarity"""
        for line in self:
            line.quantity_ordered = line.quantity_packaging
    
    def _inverse_quantity_ordered(self):
        """Write back to quantity_packaging"""
        for line in self:
            line.quantity_packaging = line.quantity_ordered
    
    @api.depends('quantity_produced', 'product_packaging_id.qty')
    def _compute_quantity_produced_units(self):
        """Convert produced packages to units"""
        for line in self:
            if line.quantity_produced and line.product_packaging_id:
                line.quantity_produced_units = (
                    line.quantity_produced * line.product_packaging_id.qty
                )
            else:
                line.quantity_produced_units = 0.0
    
    @api.depends('quantity_loaded', 'product_packaging_id.qty')
    def _compute_quantity_loaded_units(self):
        """Convert loaded packages to units"""
        for line in self:
            if line.quantity_loaded and line.product_packaging_id:
                line.quantity_loaded_units = (
                    line.quantity_loaded * line.product_packaging_id.qty
                )
            else:
                line.quantity_loaded_units = 0.0
    
    @api.depends('quantity_packaging', 'quantity_produced', 'quantity_loaded')
    def _compute_quantity_variances(self):
        """Calculate variances at each stage"""
        for line in self:
            ordered = line.quantity_packaging or 0.0
            produced = line.quantity_produced or 0.0
            loaded = line.quantity_loaded or 0.0
            
            line.quantity_variance_production = produced - ordered
            line.quantity_variance_loading = loaded - produced
            line.quantity_variance_total = loaded - ordered
    
    @api.depends('quantity_produced', 'quantity_packaging')
    def _compute_production_status(self):
        """Visual indicator for production completion"""
        for line in self:
            if not line.quantity_produced:
                line.production_status = 'pending'
            elif abs(line.quantity_produced - line.quantity_packaging) < 0.001:
                line.production_status = 'completed'
            elif abs(line.quantity_produced - line.quantity_packaging) > 0.001:
                line.production_status = 'variance'
            else:
                line.production_status = 'in_progress'
    
    @api.depends('quantity_loaded', 'quantity_produced', 'quantity_packaging')
    def _compute_loading_status(self):
        """Visual indicator for loading completion"""
        for line in self:
            if not line.quantity_loaded:
                line.loading_status = 'pending'
            else:
                # Compare loaded to produced (if available) or ordered
                expected = line.quantity_produced or line.quantity_packaging
                if abs(line.quantity_loaded - expected) < 0.001:
                    line.loading_status = 'loaded'
                else:
                    line.loading_status = 'variance'
    
    # =========================================================================
    # EXISTING METHODS (preserved from original)
    # =========================================================================
    
    @api.depends('product_packaging_id')
    def _compute_packaging_uom(self):
        """
        FIXED: Get UoM from packaging using correct field name.
        
        The product.packaging model now has 'uom_id' field that is
        auto-computed when packaging is created/modified.
        
        CRITICAL: This UoM is what gets passed to SO/PO!
        """
        for line in self:
            if not line.product_packaging_id:
                line.packaging_uom_id = False
                continue
            
            # Try to get the auto-created packaging UoM
            if hasattr(line.product_packaging_id, 'uom_id') and line.product_packaging_id.uom_id:
                line.packaging_uom_id = line.product_packaging_id.uom_id
                _logger.debug(
                    f"✓ Deal line {line.id}: Using packaging UoM '{line.packaging_uom_id.name}' "
                    f"for {line.product_packaging_id.name}"
                )
            else:
                # UoM not found - this should not happen with the fixed product_packaging model
                _logger.error(
                    f"✗ Deal line {line.id}: No UoM found for packaging '{line.product_packaging_id.name}'. "
                    f"The packaging UoM should have been auto-created!"
                )
                
                # Try to force-create it
                try:
                    line.product_packaging_id._compute_packaging_uom()
                    if line.product_packaging_id.uom_id:
                        line.packaging_uom_id = line.product_packaging_id.uom_id
                        _logger.info(
                            f"✓ Force-created UoM for packaging '{line.product_packaging_id.name}'"
                        )
                    else:
                        line.packaging_uom_id = False
                except Exception as e:
                    _logger.error(
                        f"✗ Failed to force-create UoM for packaging '{line.product_packaging_id.name}': {e}"
                    )
                    line.packaging_uom_id = False
    
    @api.depends('quantity_packaging', 'product_packaging_id')
    def _compute_quantities(self):
        """Compute unit quantities from package quantities"""
        for line in self:
            # Calculate units
            if line.product_packaging_id and line.product_packaging_id.qty:
                line.quantity_units = line.quantity_packaging * line.product_packaging_id.qty
            else:
                line.quantity_units = line.quantity_packaging
    
    @api.onchange('quantity_packaging', 'product_packaging_id', 'product_id')
    def _onchange_quantity_packaging_calculate_weight(self):
        """Calculate weight when entering by packages"""
        if self.entry_mode == 'pkg' and self.quantity_packaging and self.quantity_packaging > 0:
            if self.product_packaging_id and self.product_id and self.product_id.weight:
                # Calculate package weight
                package_weight = self.product_packaging_id.qty * self.product_id.weight
                if package_weight > 0:
                    self.weight = self.quantity_packaging * package_weight
                    _logger.debug(f"Calculated weight: {self.weight} kg from {self.quantity_packaging} packages")
    
    @api.onchange('weight', 'product_packaging_id', 'product_id')
    def _onchange_weight(self):
        """Convert kg to packages when entering by weight"""
        if self.entry_mode == 'kg' and self.weight > 0:
            if not self.product_id:
                return {
                    'warning': {
                        'title': _('Product Required'),
                        'message': _('Please select a product first.')
                    }
                }
            
            if not self.product_packaging_id:
                return {
                    'warning': {
                        'title': _('Packaging Required'),
                        'message': _('Please select packaging first.')
                    }
                }
            
            if not self.product_id.weight or self.product_id.weight == 0:
                return {
                    'warning': {
                        'title': _('Weight Not Defined'),
                        'message': _(
                            'Product %s has no weight defined. '
                            'Please update product master data or switch to package entry mode.'
                        ) % self.product_id.name
                    }
                }
            
            # Calculate package weight
            package_weight = self.product_packaging_id.qty * self.product_id.weight
            
            if package_weight == 0:
                return {
                    'warning': {
                        'title': _('Invalid Weight'),
                        'message': _('Package weight calculates to zero. Check product and packaging configuration.')
                    }
                }
            
            # Calculate packages from weight
            calculated_packages = self.weight / package_weight
            
            # Check if divisible evenly (tolerance for float precision)
            if abs(calculated_packages - round(calculated_packages)) > 0.001:
                # Calculate suggestions
                packages_floor = int(calculated_packages)
                packages_ceil = packages_floor + 1
                weight_floor = packages_floor * package_weight
                weight_ceil = packages_ceil * package_weight
                
                return {
                    'warning': {
                        'title': _('Weight Does Not Divide Evenly'),
                        'message': _(
                            'Weight %.3f kg does not divide evenly into packages.\n'
                            'Each package weighs %.3f kg.\n'
                            'Result would be %.3f packages (fractional not allowed).\n\n'
                            'Suggestions:\n'
                            '• %d packages = %.3f kg\n'
                            '• %d packages = %.3f kg\n\n'
                            'Please adjust weight or switch to package entry mode.'
                        ) % (
                            self.weight,
                            package_weight,
                            calculated_packages,
                            packages_floor, weight_floor,
                            packages_ceil, weight_ceil
                        )
                    }
                }
            
            # Set package quantity (rounded to handle float precision)
            self.quantity_packaging = round(calculated_packages)
    
    def _get_package_weight(self):
        """
        Get weight of a single package using priority chain.
        Returns 0 if weight cannot be determined.
        """
        self.ensure_one()
        
        # Priority 1: packaging.net_weight
        if (self.product_packaging_id and 
            hasattr(self.product_packaging_id, 'net_weight') and 
            self.product_packaging_id.net_weight > 0):
            return self.product_packaging_id.net_weight
        
        # Priority 2: Calculate from product weight
        if (self.product_packaging_id and 
            self.product_id and 
            self.product_packaging_id.qty and 
            self.product_id.weight > 0):
            return self.product_packaging_id.qty * self.product_id.weight
        
        # No weight info available
        return 0.0
    
    @api.onchange('quantity_packaging')
    def _onchange_quantity_packaging(self):
        """When quantity changes, check for quantity-based vendor pricing tiers"""
        if not self.quantity_packaging or not self.deal_id.supplier_id:
            return
        
        # Re-fetch supplier price (might hit different quantity tier)
        if self.product_id and self.product_packaging_id:
            self._fetch_supplier_price()
    
    @api.constrains('quantity_packaging')
    def _check_quantity(self):
        """Validate quantity is positive"""
        for line in self:
            if line.quantity_packaging <= 0:
                raise ValidationError(_("Quantity must be greater than zero"))