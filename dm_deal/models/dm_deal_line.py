# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealLine(models.Model):
    """Deal Line with package-native quantities and 6-decimal pricing"""
    _name = 'dm.deal.line'
    _description = 'Deal Line'
    _order = 'sequence, id'
    
    # =========================================================================
    # FIELDS
    # =========================================================================
    
    # Sequencing
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Parent deal
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    # Product and packaging
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('sale_ok', '=', True)]
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Packaging',
        required=True,
        domain="[('product_id', '=', product_id)]"
    )
    
    packaging_uom_id = fields.Many2one(
        'uom.uom',
        string='Package UoM',
        compute='_compute_packaging_uom',
        store=True,
        readonly=True
    )
    
    # Customer product codes
    customer_product_code = fields.Char(
        string='Customer Product Code',
        help='Customer\'s code for this product'
    )
    
    customer_product_description = fields.Text(
        string='Customer Description',
        help='Customer\'s description for this product'
    )

    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('is_company', '=', True), ('supplier_rank', '>', 0)],
        help='Supplier determined from vendor pricing for this product'
    )
    
    # =========================================================================
    # WEIGHT ENTRY ENHANCEMENT - Sprint 2.4
    # =========================================================================
    
    # Entry mode for quantity input
    entry_mode = fields.Selection([
        ('pkg', 'By Package'),
        ('kg', 'By Weight (kg)')
    ], string='Entry Mode', default='pkg', required=True)
    
    # Package-native quantities (PRIMARY)
    quantity_packaging = fields.Float(
        string='Qty (Packages)',
        digits=(16, 3),
        required=True,
        default=1.0
    )
    
    # Weight field - dual purpose (entry in kg mode, display in pkg mode)
    weight = fields.Float(
        string='Weight (kg)',
        digits=(16, 3),
        help='Enter weight in kg mode, or displays calculated weight in package mode'
    )
    
    # Unit quantities (COMPUTED REFERENCE ONLY)
    quantity_units = fields.Float(
        string='Qty (Units)',
        compute='_compute_quantities',
        store=True,
        digits=(16, 3),
        help='Reference only - calculated from packages'
    )
    
    # Container type from product
    container_type_id = fields.Many2one(
        'dm.container.type',
        string='Container Type',
        compute='_compute_container_type',
        store=True
    )
    
    # =========================================================================
    # CONTAINER CALCULATIONS - Sprint 4 (Package Configuration Extension)
    # =========================================================================
    
    containers_required = fields.Float(
        string='Containers Required',
        compute='_compute_containers_required',
        store=True,
        readonly=False,  # User can override
        digits=(16, 3),
        help='Number of containers needed (auto-calculated, can override)'
    )
    
    container_calculation_method = fields.Selection([
        ('manual', 'Manual Entry'),
        ('packaging', 'From Packaging Hierarchy'),
        ('volume', 'From Volume'),
        ('weight', 'From Weight')
    ], string='Calculation Method',
        compute='_compute_container_calculation_method',
        store=True,
        help='Shows how containers were calculated'
    )
    
    container_teu = fields.Float(
        string='TEU',
        compute='_compute_container_teu',
        store=True,
        digits=(16, 2),
        help='Twenty-foot Equivalent Units for capacity planning'
    )
    
    container_calculation_warning = fields.Char(
        string='Calculation Warning',
        compute='_compute_container_calculation_warning',
        help='Warnings about missing data or calculation issues'
    )
    
    # =========================================================================
    # SALES PRICING (6-decimal precision)
    # =========================================================================

    price_packaging_sale = fields.Float(
        string='Sale Price/Package',
        digits=(16, 6),
        required=True
    )
    
    price_unit_sale = fields.Float(
        string='Sale Price/Unit',
        compute='_compute_prices',
        store=True,
        digits=(16, 6),
        help='Reference only - calculated from package price'
    )
    
    price_per_kg_sale = fields.Float(
        string='Sale Price/kg',
        compute='_compute_prices',
        store=True,
        digits=(16, 3)
    )
    
    # Purchase pricing
    price_packaging_purchase = fields.Float(
        string='Purchase Price/Package',
        digits=(16, 6)
    )
    
    price_unit_purchase = fields.Float(
        string='Purchase Price/Unit',
        compute='_compute_prices',
        store=True,
        digits=(16, 6),
        help='Reference only - calculated from package price'
    )
    
    price_per_kg_purchase = fields.Float(
        string='Purchase Price/kg',
        compute='_compute_prices',
        store=True,
        digits=(16, 3)
    )
    
    # Amounts
    amount_sale = fields.Float(
        string='Sale Amount',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    amount_purchase = fields.Float(
        string='Purchase Amount',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    # Margin
    margin_amount = fields.Float(
        string='Margin',
        compute='_compute_amounts',
        store=True,
        digits=(16, 2)
    )
    
    margin_percentage = fields.Float(
        string='Margin %',
        compute='_compute_amounts',
        store=True,
        digits=(5, 2)
    )
    
    # Tracking quantities through stages
    quantity_produced = fields.Float(
        string='Produced (Packages)',
        digits=(16, 3),
        readonly=True,
        help='Quantity confirmed as produced'
    )
    
    quantity_loaded = fields.Float(
        string='Loaded (Packages)',
        digits=(16, 3),
        readonly=True,
        help='Quantity actually loaded for shipping'
    )
    
    quantity_invoiced = fields.Float(
        string='Invoiced (Packages)',
        digits=(16, 3),
        readonly=True,
        help='Quantity invoiced to customer'
    )
    
    production_progress = fields.Float(
        string='Production %',
        compute='_compute_progress',
        store=True,
        digits=(5, 2)
    )
    
    # Links to SO/PO lines
    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string='SO Line',
        readonly=True
    )
    
    purchase_order_line_id = fields.Many2one(
        'purchase.order.line',
        string='PO Line',
        readonly=True
    )
    
    # State-related fields
    deal_state = fields.Selection(
        related='deal_id.state',
        string='Deal Status',
        store=True
    )

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=False
    )
    
    # Notes
    notes = fields.Text(string='Notes')
    
    # =========================================================================
    # COMPUTED METHODS
    # =========================================================================
    
    @api.depends('product_id')
    def _compute_container_type(self):
        """Get container type from product's effective container type"""
        for line in self:
            if line.product_id and hasattr(line.product_id, 'effective_container_type_id'):
                line.container_type_id = line.product_id.effective_container_type_id
            else:
                line.container_type_id = False
    
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
    
    @api.depends('price_packaging_sale', 'price_packaging_purchase', 
                 'product_packaging_id', 'weight')
    def _compute_prices(self):
        """Compute unit prices and price per kg from package prices"""
        for line in self:
            # Sales prices
            if line.product_packaging_id and line.product_packaging_id.qty:
                line.price_unit_sale = line.price_packaging_sale / line.product_packaging_id.qty
                line.price_unit_purchase = line.price_packaging_purchase / line.product_packaging_id.qty
            else:
                line.price_unit_sale = line.price_packaging_sale
                line.price_unit_purchase = line.price_packaging_purchase
            
            # Price per kg
            if line.weight > 0:
                total_sale = line.quantity_packaging * line.price_packaging_sale
                total_purchase = line.quantity_packaging * line.price_packaging_purchase
                line.price_per_kg_sale = total_sale / line.weight
                line.price_per_kg_purchase = total_purchase / line.weight
            else:
                line.price_per_kg_sale = 0.0
                line.price_per_kg_purchase = 0.0
    
    @api.depends('quantity_packaging', 'price_packaging_sale', 'price_packaging_purchase', 
                 'product_packaging_id', 'product_id.weight')
    def _compute_amounts(self):
        """Compute all amounts from package quantities and prices"""
        for line in self:
            # Sales calculations
            if line.quantity_packaging and line.price_packaging_sale:
                line.amount_sale = line.quantity_packaging * line.price_packaging_sale
                
                if line.product_packaging_id and line.product_packaging_id.qty:
                    line.quantity_units = line.quantity_packaging * line.product_packaging_id.qty
                    line.price_unit_sale = line.price_packaging_sale / line.product_packaging_id.qty
                else:
                    line.quantity_units = 0
                    line.price_unit_sale = 0
                
                # Price per kg
                if line.product_id.weight and line.quantity_units:
                    total_weight = line.quantity_units * line.product_id.weight
                    if total_weight > 0:
                        line.price_per_kg_sale = line.amount_sale / total_weight
                    else:
                        line.price_per_kg_sale = 0
                else:
                    line.price_per_kg_sale = 0
            else:
                line.amount_sale = 0
                line.quantity_units = 0
                line.price_unit_sale = 0
                line.price_per_kg_sale = 0
            
            # Purchase calculations
            if line.quantity_packaging and line.price_packaging_purchase:
                line.amount_purchase = line.quantity_packaging * line.price_packaging_purchase
                
                if line.product_packaging_id and line.product_packaging_id.qty:
                    line.price_unit_purchase = line.price_packaging_purchase / line.product_packaging_id.qty
                else:
                    line.price_unit_purchase = 0
                
                # Price per kg
                if line.product_id.weight and line.quantity_units:
                    total_weight = line.quantity_units * line.product_id.weight
                    if total_weight > 0:
                        line.price_per_kg_purchase = line.amount_purchase / total_weight
                    else:
                        line.price_per_kg_purchase = 0
                else:
                    line.price_per_kg_purchase = 0
            else:
                line.amount_purchase = 0
                line.price_unit_purchase = 0
                line.price_per_kg_purchase = 0
            
            # Margin calculations
            line.margin_amount = line.amount_sale - line.amount_purchase
            
            if line.amount_sale > 0:
                # CRITICAL FIX: Store as fraction (0.155) not percentage (15.5)
                # Because widget="percentage" expects fraction
                line.margin_percentage = (line.margin_amount / line.amount_sale)
            else:
                line.margin_percentage = 0
    
    @api.depends('quantity_produced', 'quantity_packaging')
    def _compute_progress(self):
        """Compute production progress percentage"""
        for line in self:
            if line.quantity_packaging > 0:
                line.production_progress = (line.quantity_produced / line.quantity_packaging) * 100
            else:
                line.production_progress = 0.0

    @api.depends('product_id', 'product_id.display_name', 
                 'quantity_packaging', 'packaging_uom_id', 'packaging_uom_id.name')
    def _compute_display_name(self):
        """Compute display name for Odoo 17"""
        for line in self:
            if line.product_id:
                pkg_info = f"{line.quantity_packaging:.2f} {line.packaging_uom_id.name if line.packaging_uom_id else 'pkg'}"
                line.display_name = f"{line.product_id.display_name} - {pkg_info}"
            else:
                line.display_name = f"Deal Line #{line.id}" if line.id else "New Line"
    
    # =========================================================================
    # CONTAINER CALCULATION METHODS - Sprint 4
    # =========================================================================
    
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
    
    # =========================================================================
    # WEIGHT ENTRY MODE METHODS - Sprint 2.4 (SYNCHRONIZED WITH WIZARD)
    # =========================================================================
    
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
    
    # =========================================================================
    # PRICING METHODS - SPRINT 2.3 ARCHITECTURE
    # =========================================================================
    
    def _fetch_customer_price(self):
        """
        Fetch customer price from dm.customer.pricelist convenience model.
        This model auto-syncs to product.pricelist.item.
        """
        if not self.product_id or not self.product_packaging_id or not self.deal_id.customer_id:
            _logger.debug("Skipping customer price fetch: missing product, packaging, or customer")
            return
        
        try:
            # Search dm.customer.pricelist (convenience model)
            pricelist_item = self.env['dm.customer.pricelist'].search([
                ('partner_id', '=', self.deal_id.customer_id.id),
                ('product_id', '=', self.product_id.id),
                ('product_packaging_id', '=', self.product_packaging_id.id),
                ('active', '=', True),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ], limit=1)
            
            if pricelist_item:
                # Get package price (PRIMARY - never compute from units)
                self.price_packaging_sale = pricelist_item.package_price
                self.customer_product_code = pricelist_item.customer_product_code or self.customer_product_code
                self.customer_product_description = pricelist_item.customer_product_description or self.customer_product_description
                
                # Currency validation
                if pricelist_item.currency_id and not self.deal_id.currency_id:
                    # Auto-set deal currency from first product
                    self.deal_id.currency_id = pricelist_item.currency_id
                elif pricelist_item.currency_id and pricelist_item.currency_id != self.deal_id.currency_id:
                    raise ValidationError(
                        f"Currency mismatch: Customer price for '{self.product_id.name}' is in "
                        f"{pricelist_item.currency_id.name}, but deal is in {self.deal_id.currency_id.name}"
                    )
                
                _logger.info(
                    f"Fetched customer price: {self.price_packaging_sale} "
                    f"for {self.product_id.name} ({self.product_packaging_id.name})"
                )
            else:
                _logger.warning(
                    f"No customer price found for {self.deal_id.customer_id.name} / "
                    f"{self.product_id.name} / {self.product_packaging_id.name}"
                )
        
        except ValidationError:
            raise
        except Exception as e:
            _logger.error(f"Error fetching customer price: {str(e)}", exc_info=True)
    
    def _fetch_supplier_price(self):
        """
        Fetch supplier price from vendor pricing (product.supplierinfo with dm_ fields).
        Also sets line.supplier_id from the price record.
        """
        _logger.warning("💰 _fetch_supplier_price CALLED")
        _logger.warning(f"   Product: {self.product_id.name if self.product_id else 'None'}")
        _logger.warning(f"   Packaging: {self.product_packaging_id.name if self.product_packaging_id else 'None'}")
        _logger.warning(f"   Line supplier (before): {self.supplier_id.name if self.supplier_id else 'NOT SET'}")
        _logger.warning(f"   Deal supplier: {self.deal_id.supplier_id.name if self.deal_id.supplier_id else 'NOT SET'}")
        
        if not self.product_id or not self.product_packaging_id:
            _logger.warning("   ❌ Missing product or packaging")
            return
        
        try:
            # Search for supplier info
            supplier_infos = self.env['product.supplierinfo'].search([
                '|',
                    ('product_id', '=', self.product_id.id),
                    '&',
                        ('product_id', '=', False),
                        ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ], order='sequence, min_qty, price')
            
            if not supplier_infos:
                _logger.warning("   ❌ No supplier info found")
                raise UserError(
                    f"No vendor pricing found for product '{self.product_id.name}'.\n\n"
                    f"Please configure vendor pricing in the product's Purchase tab."
                )
            
            unique_suppliers = supplier_infos.mapped('partner_id')
            supplier_count = len(unique_suppliers)
            
            _logger.warning(f"   Found {supplier_count} suppliers with pricing:")
            for sup in unique_suppliers:
                _logger.warning(f"      - {sup.name}")
            
            # PRIORITY 1: Filter by deal's supplier if set (Line 2+)
            if self.deal_id.supplier_id:
                _logger.warning(f"   Filtering by deal supplier: {self.deal_id.supplier_id.name}")
                supplier_infos = supplier_infos.filtered(
                    lambda si: si.partner_id == self.deal_id.supplier_id
                )
                if not supplier_infos:
                    raise UserError(
                        f"Product '{self.product_id.name}' has no pricing from "
                        f"deal supplier '{self.deal_id.supplier_id.name}'"
                    )
            
            # PRIORITY 2: Filter by line's supplier if already set
            elif self.supplier_id:
                _logger.warning(f"   Filtering by line supplier: {self.supplier_id.name}")
                supplier_infos = supplier_infos.filtered(
                    lambda si: si.partner_id == self.supplier_id
                )
                if not supplier_infos:
                    _logger.warning(f"   ⚠️ Line supplier has no pricing - resetting to all")
                    supplier_infos = self.env['product.supplierinfo'].search([
                        '|',
                            ('product_id', '=', self.product_id.id),
                            '&',
                                ('product_id', '=', False),
                                ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
                    ], order='sequence, min_qty, price')
            
            # Find exact package match
            best_info = None
            
            _logger.warning(f"   Looking for package-based pricing for: {self.product_packaging_id.name}")
            
            for info in supplier_infos:
                if info.dm_is_package_price and info.dm_packaging_id == self.product_packaging_id:
                    best_info = info
                    _logger.warning(f"   ✅ Found exact package match: {info.partner_id.name}")
                    break
            
            if not best_info:
                # No exact match - check what's available
                package_infos = supplier_infos.filtered(lambda si: si.dm_is_package_price)
                
                if package_infos:
                    _logger.warning(f"   ⚠️ No exact package match for {self.product_packaging_id.name}")
                    _logger.warning(f"   Available package-based prices:")
                    for pi in package_infos:
                        _logger.warning(f"      - {pi.dm_packaging_id.name}: ${pi.dm_package_price:.6f} ({pi.partner_id.name})")
                    
                    available = ', '.join(f"{pi.dm_packaging_id.name} ({pi.partner_id.name})" 
                                        for pi in package_infos)
                    raise UserError(
                        f"No vendor price for packaging '{self.product_packaging_id.name}'.\n\n"
                        f"Product: {self.product_id.name}\n"
                        f"Available packagings:\n{available}\n\n"
                        f"Please configure vendor pricing for this specific packaging."
                    )
                else:
                    # No package-based pricing - use standard price
                    best_info = supplier_infos[0]
                    _logger.warning(f"   ⚠️ No package-based pricing found - using standard supplierinfo")
            
            if not best_info:
                raise UserError(f"No vendor pricing found")
            
            # SET SUPPLIER ON LINE
            if not self.supplier_id:
                self.supplier_id = best_info.partner_id
                _logger.warning(f"   ✅ SET line.supplier_id = {self.supplier_id.name}")
            
            # GET PRICE
            if best_info.dm_is_package_price and best_info.dm_package_price:
                # Use package-based price
                self.price_packaging_purchase = best_info.dm_package_price
                _logger.warning(f"   ✅ Package price: ${self.price_packaging_purchase:.6f} per {best_info.dm_packaging_id.name}")
            elif best_info.price and self.product_packaging_id.qty:
                # Calculate from unit price
                self.price_packaging_purchase = best_info.price * self.product_packaging_id.qty
                _logger.warning(f"   ✅ Calculated package price from unit: ${self.price_packaging_purchase:.6f}")
            else:
                self.price_packaging_purchase = 0
                _logger.warning(f"   ⚠️ No price available - set to 0")
        
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Error fetching supplier price: {str(e)}", exc_info=True)
            raise UserError(f"Error fetching supplier price: {str(e)}")
    
    # =========================================================================
    # ONCHANGE METHODS
    # =========================================================================
    
    @api.onchange('customer_product_code')
    def _onchange_customer_product_code(self):
        """Look up product by customer code and auto-populate fields"""
        if not self.customer_product_code or not self.deal_id.customer_id:
            return
        
        try:
            # Search in dm.customer.pricelist
            pricelist_item = self.env['dm.customer.pricelist'].search([
                ('partner_id', '=', self.deal_id.customer_id.id),
                ('customer_product_code', '=', self.customer_product_code),
                ('active', '=', True),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ], limit=1)
            
            if pricelist_item:
                # Auto-populate product and packaging
                self.product_id = pricelist_item.product_id
                self.product_packaging_id = pricelist_item.product_packaging_id
                self.price_packaging_sale = pricelist_item.package_price
                self.customer_product_description = pricelist_item.customer_product_description
                
                # Set deal currency if not set
                if not self.deal_id.currency_id and pricelist_item.currency_id:
                    self.deal_id.currency_id = pricelist_item.currency_id
                
                # Smart-select supplier
                self._smart_select_supplier()
                
                _logger.info(f"Found product by customer code '{self.customer_product_code}': {pricelist_item.product_id.name}")
            else:
                _logger.warning(f"No product found for customer code '{self.customer_product_code}'")
        
        except Exception as e:
            _logger.error(f"Error looking up customer product code: {str(e)}")
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """When product changes, select default packaging and fetch prices"""
        if not self.product_id:
            return
        
        # Set default packaging
        if self.product_id.packaging_ids:
            try:
                # Try to find 'case' packaging
                case_packaging = self.product_id.packaging_ids.filtered(
                    lambda p: hasattr(p, 'standard_type_id') and p.standard_type_id and p.standard_type_id.code == 'case'
                )
                if case_packaging:
                    self.product_packaging_id = case_packaging[0]
                else:
                    # Fallback to first packaging
                    self.product_packaging_id = self.product_id.packaging_ids[0]
            except Exception as e:
                _logger.warning(f"Error selecting default packaging: {str(e)}")
                self.product_packaging_id = self.product_id.packaging_ids[0]
    
    @api.onchange('product_packaging_id')
    def _onchange_product_packaging_id(self):
        """When packaging changes - simplified flow"""
        _logger.warning("=" * 80)
        _logger.warning("🔍 _onchange_product_packaging_id TRIGGERED")
        _logger.warning(f"   Product: {self.product_id.name if self.product_id else 'None'}")
        _logger.warning(f"   Packaging: {self.product_packaging_id.name if self.product_packaging_id else 'None'}")
        
        if not self.product_packaging_id or not self.product_id:
            return
        
        # Fetch customer price
        if self.deal_id.customer_id:
            _logger.warning("   💰 Fetching customer price")
            self._fetch_customer_price()
        
        # Fetch supplier price (this also sets line.supplier_id!)
        _logger.warning("   💰 Fetching supplier price (also sets supplier)")
        self._fetch_supplier_price()
        
        _logger.warning(f"   Line supplier after price fetch: {self.supplier_id.name if self.supplier_id else 'NOT SET'}")
        
        # Validate supplier consistency for Line 2+
        if self.deal_id.supplier_id and self.supplier_id:
            if self.deal_id.supplier_id != self.supplier_id:
                _logger.warning("   ❌ SUPPLIER MISMATCH!")
                raise UserError(
                    f"Cannot add this product!\n\n"
                    f"Deal supplier: {self.deal_id.supplier_id.name}\n"
                    f"Product supplier: {self.supplier_id.name}\n\n"
                    f"Cannot mix suppliers in one deal."
                )
        
        # Trigger template application for Line 1
        if self.deal_id and not self.deal_id.template_id and not self.deal_id.template_selection_pending:
            _logger.warning("   📋 Triggering template application")
            result = self.deal_id._apply_template_from_lines()
            _logger.warning("=" * 80)
            if result:
                return result
        
        _logger.warning("=" * 80)
    
    @api.onchange('quantity_packaging')
    def _onchange_quantity_packaging(self):
        """When quantity changes, check for quantity-based vendor pricing tiers"""
        if not self.quantity_packaging or not self.deal_id.supplier_id:
            return
        
        # Re-fetch supplier price (might hit different quantity tier)
        if self.product_id and self.product_packaging_id:
            self._fetch_supplier_price()
    
    # =========================================================================
    # SUPPLIER SELECTION LOGIC
    # =========================================================================
    
    def _smart_select_supplier(self):
        """
        Determine supplier from vendor pricing.
        
        Returns:
            dict: Update commands for parent deal if supplier should be set
        """
        if not self.product_id or not self.product_packaging_id:
            return {}
        
        try:
            supplier_infos = self.env['product.supplierinfo'].search([
                '|',
                    ('product_id', '=', self.product_id.id),
                    '&',
                        ('product_id', '=', False),
                        ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ])
            
            if not supplier_infos:
                raise UserError(
                    f"No vendor pricing found for product '{self.product_id.name}'.\n\n"
                    f"Please configure vendor pricing in the product's Purchase tab."
                )
            
            unique_suppliers = supplier_infos.mapped('partner_id')
            supplier_count = len(unique_suppliers)
            
            # Case 1: Deal already has supplier set
            if self.deal_id.supplier_id:
                if self.deal_id.supplier_id not in unique_suppliers:
                    available = ', '.join(unique_suppliers.mapped('name'))
                    raise UserError(
                        f"Product '{self.product_id.name}' is not available from current supplier "
                        f"'{self.deal_id.supplier_id.name}'.\n\n"
                        f"Available suppliers: {available}\n\n"
                        f"Cannot mix suppliers in one deal."
                    )
                _logger.warning(f"   ✅ Supplier already set: {self.deal_id.supplier_id.name}")
                return {}
            
            # Case 2: Single supplier - SET IT
            if supplier_count == 1:
                supplier = unique_suppliers[0]
                _logger.warning(f"   ✅ Single supplier found: {supplier.name} - SETTING ON DEAL")
                
                # CRITICAL: Return value to update parent deal
                return {
                    'value': {
                        'supplier_id': supplier.id
                    }
                }
            
            # Case 3: Multiple suppliers - defer to template selection
            else:
                _logger.warning(f"   ⚠️ Multiple suppliers ({supplier_count}) - will choose via template")
                return {}
        
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Error in supplier selection: {str(e)}", exc_info=True)
            return {}
    
    # =========================================================================
    # CONSTRAINTS
    # =========================================================================
    
    @api.constrains('quantity_packaging')
    def _check_quantity(self):
        """Validate quantity is positive"""
        for line in self:
            if line.quantity_packaging <= 0:
                raise ValidationError(_("Quantity must be greater than zero"))
    
    @api.constrains('price_packaging_sale', 'price_packaging_purchase')
    def _check_prices(self):
        """Validate prices are not negative"""
        for line in self:
            if line.price_packaging_sale < 0:
                raise ValidationError(_("Sale price cannot be negative"))
            if line.price_packaging_purchase < 0:
                raise ValidationError(_("Purchase price cannot be negative"))
    
    # =========================================================================
    # DISPLAY
    # =========================================================================
    
    def name_get(self):
        """Display name for deal lines"""
        result = []
        for line in self:
            name = f"{line.product_id.display_name} - {line.quantity_packaging:.2f} {line.packaging_uom_id.name if line.packaging_uom_id else 'pkg'}"
            result.append((line.id, name))
        return result