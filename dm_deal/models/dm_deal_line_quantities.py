# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDealLineQuantities(models.Model):
    """Deal Line - Quantities & Lot Tracking Extension
    
    Single source of truth: lot_ids (One2many)
    Smart inline editing with auto-create logic
    """
    _inherit = 'dm.deal.line'
    _description = 'Deal Line - Quantities & Lot Extension'
    
    # =========================================================================
    # THREE-QUANTITY SYSTEM - PACKAGE-NATIVE
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
    
    # Production tracking (package-based) - OPTIONAL
    quantity_produced = fields.Float(
        string='Quantity Produced',
        digits=(16, 3),
        tracking=True,
        help="Optional: Actual quantity produced by factory (in packages)"
    )
    
    # Loading tracking (package-based) - CRITICAL FOR INVOICING
    quantity_loaded = fields.Float(
        string='Quantity Loaded',
        digits=(16, 3),
        tracking=True,
        help="CRITICAL: Actual quantity loaded and shipped (in packages) - basis for invoicing"
    )
    
    # Variance tracking (all in packages)
    quantity_variance_production = fields.Float(
        string='Production Variance',
        compute='_compute_quantity_variances',
        store=True,
        digits=(16, 3),
        help="Difference between ordered and produced (packages)"
    )
    
    quantity_variance_loading = fields.Float(
        string='Loading Variance',
        compute='_compute_quantity_variances',
        store=True,
        digits=(16, 3),
        help="Difference between produced and loaded (packages)"
    )
    
    quantity_variance_total = fields.Float(
        string='Total Variance',
        compute='_compute_quantity_variances',
        store=True,
        digits=(16, 3),
        help="Difference between ordered and loaded (packages)"
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
    # LOADED AMOUNTS (MONETARY VALUES)
    # =========================================================================
    
    amount_loaded_sale = fields.Float(
        string='Loaded Amount (Sale)',
        compute='_compute_loaded_amounts',
        store=True,
        digits=(16, 2),
        help="Value of loaded quantity - basis for customer invoicing"
    )
    
    amount_loaded_purchase = fields.Float(
        string='Loaded Amount (Purchase)',
        compute='_compute_loaded_amounts',
        store=True,
        digits=(16, 2),
        help="Value of loaded quantity - expected supplier invoice"
    )
    
    # =========================================================================
    # LOT TRACKING - ONE2MANY ONLY (SINGLE SOURCE OF TRUTH)
    # =========================================================================
    
    lot_ids = fields.One2many(
        'dm.deal.line.lot',
        'deal_line_id',
        string='Production Lots'
    )
    
    lot_count = fields.Integer(
        compute='_compute_lot_info',
        string='# Lots',
        store=True
    )
    
    has_multiple_lots = fields.Boolean(
        compute='_compute_lot_info',
        string='Multiple Lots',
        store=True,
        help="True if line has multiple lot records"
    )

    total_lotted_quantity = fields.Float(
        compute='_compute_lot_info',
        string='Total Lotted',
        digits=(16, 3),
        store=True,
        help="Sum of quantities from lot records"
    )

    lots_info_display = fields.Char(
        compute='_compute_lot_info',
        string='Lots Summary',
        store=True,
        help="Summary of lot information for display"
    )
    
    # =========================================================================
    # QUICK ENTRY FIELDS (TRANSIENT - CREATE LOT ON SAVE)
    # =========================================================================
    
    quick_lot_number = fields.Char(
        string='Quick Lot #',
        compute='_compute_quick_fields_from_lot',
        inverse='_inverse_quick_lot_number',
        store=False,
        help='Enter lot number - creates/updates lot record on save'
    )

    quick_production_date = fields.Date(
        string='Quick Prod Date',
        compute='_compute_quick_fields_from_lot',
        inverse='_inverse_quick_production_date',
        store=False,
        help='Production date for quick lot entry'
    )

    quick_expiry_date = fields.Date(
        string='Quick Expiry',
        compute='_compute_quick_fields_from_lot',
        inverse='_inverse_quick_expiry_date',
        store=False,
        help='Expiry date for quick lot entry (auto-calculated if blank)'
    )
    
    # =========================================================================
    # DISPLAY FIELDS (COMPUTED FROM LOT_IDS)
    # =========================================================================
    
    lot_number_display = fields.Char(
        string='Lot # Display',
        compute='_compute_lot_display_fields',
        store=False,
        help='Shows actual lot number, "Multiple (X)", or blank'
    )
    
    lot_production_date_display = fields.Char(
        string='Prod Date Display',
        compute='_compute_lot_display_fields',
        store=False,
        help='Shows production date, "Various", or blank'
    )
    
    lot_expiry_date_display = fields.Char(
        string='Expiry Display',
        compute='_compute_lot_display_fields',
        store=False,
        help='Shows expiry date, "Various", or blank'
    )
    
    # =========================================================================
    # CONTAINER CALCULATIONS (from dm_deal_line_container.py)
    # =========================================================================
    
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
        """Enhanced create with weight/quantity sync and auto-lot creation"""
        
        # STEP 1: Sync weight ↔ quantity_packaging before creation
        for vals in vals_list:
            # If creating with weight but no quantity_packaging (kg mode)
            if vals.get('entry_mode') == 'kg' and vals.get('weight'):
                product = self.env['product.product'].browse(vals.get('product_id'))
                packaging = self.env['product.packaging'].browse(vals.get('product_packaging_id'))
                
                if product and packaging:
                    package_weight = packaging.qty * product.weight if product.weight else 0.0
                    if package_weight > 0:
                        vals['quantity_packaging'] = vals['weight'] / package_weight
            
            # If creating with quantity_packaging but no weight (pkg mode)
            elif vals.get('entry_mode') == 'pkg' and vals.get('quantity_packaging'):
                product = self.env['product.product'].browse(vals.get('product_id'))
                packaging = self.env['product.packaging'].browse(vals.get('product_packaging_id'))
                
                if product and packaging:
                    package_weight = packaging.qty * product.weight if product.weight else 0.0
                    if package_weight > 0:
                        vals['weight'] = vals['quantity_packaging'] * package_weight
        
        # STEP 2: Create records
        lines = super().create(vals_list)
        
        # STEP 3: Force container type computation (computed fields may not trigger during create)
        for line in lines:
            line._compute_container_type()
            line._compute_containers_required()
            line._compute_container_teu()
        
        # STEP 4: Process quick lot fields after creation
        for line in lines:
            line._process_quick_lot_fields()
        
        return lines
    
    def write(self, vals):
        """Enhanced write with auto-lot update from quick fields"""
        res = super().write(vals)
        
        # Process quick fields if any were changed
        quick_fields = {'quick_lot_number', 'quick_production_date', 'quick_expiry_date'}
        if set(vals.keys()) & quick_fields:
            for line in self:
                line._process_quick_lot_fields()
        
        return res
    
    # =========================================================================
    # LOT DISPLAY LOGIC
    # =========================================================================
    
    @api.depends('lot_ids', 'lot_ids.lot_number', 'lot_ids.production_date', 'lot_ids.expiry_date')
    def _compute_lot_display_fields(self):
        """Compute display fields based on lot count"""
        for line in self:
            lot_count = len(line.lot_ids)
            
            if lot_count == 0:
                # No lots yet - show blank
                line.lot_number_display = ''
                line.lot_production_date_display = ''
                line.lot_expiry_date_display = ''
            
            elif lot_count == 1:
                # Single lot - show actual data
                lot = line.lot_ids[0]
                line.lot_number_display = lot.lot_number or ''
                line.lot_production_date_display = lot.production_date.strftime('%Y-%m-%d') if lot.production_date else ''
                line.lot_expiry_date_display = lot.expiry_date.strftime('%Y-%m-%d') if lot.expiry_date else ''
            
            else:
                # Multiple lots - show indicator
                line.lot_number_display = f'Multiple ({lot_count})'
                line.lot_production_date_display = 'Various'
                line.lot_expiry_date_display = 'Various'
    
    @api.depends('lot_ids', 'lot_ids.lot_number', 'lot_ids.production_date', 'lot_ids.expiry_date')
    def _compute_quick_fields_from_lot(self):
        """Populate quick fields from single lot for editing"""
        for line in self:
            if line.lot_count == 1:
                lot = line.lot_ids[0]
                line.quick_lot_number = lot.lot_number
                line.quick_production_date = lot.production_date
                line.quick_expiry_date = lot.expiry_date
            else:
                line.quick_lot_number = False
                line.quick_production_date = False
                line.quick_expiry_date = False    
    
    @api.depends('lot_ids', 'lot_ids.quantity')
    def _compute_lot_info(self):
        """Compute lot summary information"""
        for line in self:
            lot_count = len(line.lot_ids)
            line.lot_count = lot_count
            line.has_multiple_lots = lot_count > 1
            line.total_lotted_quantity = sum(line.lot_ids.mapped('quantity'))
            
            # Build summary string
            if lot_count == 0:
                line.lots_info_display = 'No lots'
            elif lot_count == 1:
                lot = line.lot_ids[0]
                line.lots_info_display = f'{lot.lot_number} ({lot.quantity:.2f} pkg)'
            else:
                line.lots_info_display = f'{lot_count} lots ({line.total_lotted_quantity:.2f} pkg total)'
    
    # =========================================================================
    # QUICK LOT PROCESSING
    # =========================================================================
    
    def _process_quick_lot_fields(self):
        """Process quick entry fields - create or update lot record"""
        self.ensure_one()
        
        # Skip if no quick lot number entered
        if not self.quick_lot_number:
            return
        
        # Auto-calculate expiry if not provided
        expiry_date = self.quick_expiry_date
        if not expiry_date and self.quick_production_date and self.product_id:
            product_tmpl = self.product_id.product_tmpl_id
            if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                expiry_date = self.quick_production_date + timedelta(days=product_tmpl.production_to_expiry_days)
        
        # Use quantity_loaded as lot quantity (or quantity_packaging as fallback)
        lot_quantity = self.quantity_loaded or self.quantity_packaging
        
        if self.lot_count == 0:
            # Create new lot
            self.env['dm.deal.line.lot'].create({
                'deal_line_id': self.id,
                'lot_number': self.quick_lot_number,
                'quantity': lot_quantity,
                'production_date': self.quick_production_date or fields.Date.today(),
                'expiry_date': expiry_date,
            })
            _logger.info(f'Created lot {self.quick_lot_number} for deal line {self.id}')
        
        elif self.lot_count == 1:
            # Update existing single lot
            lot = self.lot_ids[0]
            lot.write({
                'lot_number': self.quick_lot_number,
                'quantity': lot_quantity,
                'production_date': self.quick_production_date or fields.Date.today(),
                'expiry_date': expiry_date,
            })
            _logger.info(f'Updated lot {self.quick_lot_number} for deal line {self.id}')
        
        else:
            # Multiple lots exist - should use wizard instead
            raise UserError(_(
                'This line has multiple lots. Please use the Manage Lots wizard (📋 button) to edit lot information.'
            ))
    
    def _inverse_quick_lot_number(self):
        """Trigger lot processing when quick field changes"""
        for line in self:
            if line.quick_lot_number:
                line._process_quick_lot_fields()

    def _inverse_quick_production_date(self):
        """Trigger lot processing when quick field changes"""
        for line in self:
            if line.quick_production_date:
                line._process_quick_lot_fields()

    def _inverse_quick_expiry_date(self):
        """Trigger lot processing when quick field changes"""
        for line in self:
            if line.quick_expiry_date:
                line._process_quick_lot_fields()    
    
    # =========================================================================
    # COMPUTED METHODS - QUANTITIES
    # =========================================================================
    
    @api.depends('quantity_packaging')
    def _compute_quantity_ordered(self):
        """Semantic alias computation"""
        for line in self:
            line.quantity_ordered = line.quantity_packaging
    
    def _inverse_quantity_ordered(self):
        """Allow setting via quantity_ordered field"""
        for line in self:
            line.quantity_packaging = line.quantity_ordered
    
    @api.depends('quantity_packaging', 'quantity_produced', 'quantity_loaded')
    def _compute_quantity_variances(self):
        """Calculate variances between quantities"""
        for line in self:
            line.quantity_variance_production = line.quantity_produced - line.quantity_packaging if line.quantity_produced else 0.0
            line.quantity_variance_loading = line.quantity_loaded - line.quantity_produced if line.quantity_loaded and line.quantity_produced else 0.0
            line.quantity_variance_total = line.quantity_loaded - line.quantity_packaging if line.quantity_loaded else 0.0
    
    @api.depends('quantity_loaded', 'quantity_packaging')
    def _compute_loading_status(self):
        """Determine loading status"""
        for line in self:
            if not line.quantity_loaded:
                line.loading_status = 'pending'
            elif abs(line.quantity_loaded - line.quantity_packaging) > 0.001:
                line.loading_status = 'variance'
            else:
                line.loading_status = 'loaded'
    
    @api.depends('quantity_loaded', 'price_packaging_sale', 'price_packaging_purchase')
    def _compute_loaded_amounts(self):
        """Calculate monetary value of loaded quantities"""
        for line in self:
            line.amount_loaded_sale = line.quantity_loaded * line.price_packaging_sale
            line.amount_loaded_purchase = line.quantity_loaded * line.price_packaging_purchase
    
    @api.depends('product_packaging_id')
    def _compute_packaging_uom(self):
        """Get UoM from packaging"""
        for line in self:
            line.packaging_uom_id = line.product_packaging_id.product_uom_id if line.product_packaging_id else False
    
    @api.depends('quantity_packaging', 'product_packaging_id.qty')
    def _compute_quantities(self):
        """Calculate unit quantities and weight from packages"""
        for line in self:
            packaging_qty = line.product_packaging_id.qty if line.product_packaging_id else 1.0
            line.quantity_units = line.quantity_packaging * packaging_qty
            
            # Calculate weight if in package mode
            if line.entry_mode == 'pkg':
                line.weight = line.quantity_packaging * line._get_package_weight()
    
    @api.depends('price_packaging_sale', 'price_packaging_purchase', 'product_packaging_id.qty', 'product_id.weight')
    def _compute_prices(self):
        """Calculate per-unit and per-kg prices"""
        for line in self:
            packaging_qty = line.product_packaging_id.qty if line.product_packaging_id else 1.0
            
            # Per-unit prices
            line.price_unit_sale = line.price_packaging_sale / packaging_qty if packaging_qty else 0.0
            line.price_unit_purchase = line.price_packaging_purchase / packaging_qty if packaging_qty else 0.0
            
            # Per-kg prices
            package_weight = line._get_package_weight()
            if package_weight > 0:
                line.price_per_kg_sale = line.price_packaging_sale / package_weight
                line.price_per_kg_purchase = line.price_packaging_purchase / package_weight
            else:
                line.price_per_kg_sale = 0.0
                line.price_per_kg_purchase = 0.0
    
    @api.depends('quantity_packaging', 'price_packaging_sale', 'price_packaging_purchase')
    def _compute_amounts(self):
        """Calculate amounts and margins"""
        for line in self:
            line.amount_sale = line.quantity_packaging * line.price_packaging_sale
            line.amount_purchase = line.quantity_packaging * line.price_packaging_purchase
            line.margin_amount = line.amount_sale - line.amount_purchase
            
            if line.amount_sale:
                line.margin_percentage = (line.margin_amount / line.amount_sale) * 100
            else:
                line.margin_percentage = 0.0
    
    @api.depends('quantity_produced', 'quantity_packaging')
    def _compute_progress(self):
        """Calculate production progress percentage"""
        for line in self:
            if line.quantity_packaging:
                line.production_progress = (line.quantity_produced / line.quantity_packaging) * 100
            else:
                line.production_progress = 0.0
    
    # =========================================================================
    # CONTAINER CALCULATIONS
    # =========================================================================
    
    @api.depends('quantity_packaging', 'product_packaging_id', 'container_type_id')
    def _compute_containers_required(self):
        """Calculate containers using hierarchy"""
        for line in self:
            if not line.quantity_packaging or not line.container_type_id:
                line.containers_required = 0.0
                continue
            
            # Try packaging hierarchy first
            containers = line._calculate_from_packaging_hierarchy()
            if containers:
                line.containers_required = containers
                continue
            
            # Fallback to volume
            containers = line._calculate_from_volume()
            if containers:
                line.containers_required = containers
                continue
            
            # Last resort: weight
            containers = line._calculate_from_weight()
            line.containers_required = containers if containers else 0.0
    
    def _calculate_from_packaging_hierarchy(self):
        """Calculate containers from packaging relationship"""
        self.ensure_one()
        
        if not self.product_packaging_id or not self.container_type_id:
            return 0.0
        
        # Method 1: Check if product has cartons_per_container configured
        product_tmpl = self.product_id.product_tmpl_id
        if (hasattr(product_tmpl, 'cartons_per_container') and 
            product_tmpl.cartons_per_container > 0 and
            hasattr(product_tmpl, 'effective_container_type_id') and
            product_tmpl.effective_container_type_id == self.container_type_id):
            
            # Direct calculation: packages / packages_per_container
            return self.quantity_packaging / product_tmpl.cartons_per_container
        
        # Method 2: Walk up packaging hierarchy (original logic)
        current = self.product_packaging_id
        while current:
            if hasattr(current, 'container_type_id') and current.container_type_id == self.container_type_id:
                if hasattr(current, 'qty') and current.qty > 0:
                    return self.quantity_packaging / current.qty
            
            current = current.package_type_id if hasattr(current, 'package_type_id') else False
        
        return 0.0

    def _calculate_from_volume(self):
        """Calculate containers from volume"""
        self.ensure_one()
        
        if not self.product_packaging_id or not self.container_type_id:
            return 0.0
        
        pkg_volume = getattr(self.product_packaging_id, 'volume', 0.0)
        container_volume = getattr(self.container_type_id, 'internal_volume', 0.0)  # ← FIXED
        
        if pkg_volume > 0 and container_volume > 0:
            total_volume = self.quantity_packaging * pkg_volume
            return total_volume / container_volume
        
        return 0.0

    def _calculate_from_weight(self):
        """Calculate containers from weight"""
        self.ensure_one()
        
        if not self.container_type_id:
            return 0.0
        
        package_weight = self._get_package_weight()
        max_payload = getattr(self.container_type_id, 'max_payload', 0.0)  # ← FIXED
        
        if package_weight > 0 and max_payload > 0:
            total_weight = self.quantity_packaging * package_weight
            return total_weight / max_payload
        
        return 0.0
    
    @api.depends('containers_required', 'product_packaging_id', 'container_type_id')
    def _compute_container_calculation_method(self):
        """Determine which calculation method was used"""
        for line in self:
            if line.containers_required == 0:
                line.container_calculation_method = 'manual'
            elif line._calculate_from_packaging_hierarchy():
                line.container_calculation_method = 'packaging'
            elif line._calculate_from_volume():
                line.container_calculation_method = 'volume'
            elif line._calculate_from_weight():
                line.container_calculation_method = 'weight'
            else:
                line.container_calculation_method = 'manual'
    
    @api.depends('containers_required', 'container_type_id.teu_factor')
    def _compute_container_teu(self):
        """Calculate TEU from containers and container type"""
        for line in self:
            teu_factor = getattr(line.container_type_id, 'teu_factor', 1.0) if line.container_type_id else 1.0
            line.container_teu = line.containers_required * teu_factor
    
    @api.depends('product_packaging_id', 'container_type_id', 'quantity_packaging')
    def _compute_container_calculation_warning(self):
        """Generate warnings about missing data"""
        for line in self:
            warnings = []
            
            if line.quantity_packaging and not line.container_type_id:
                warnings.append('No container type assigned')
            
            if line.container_type_id and not line._get_package_weight():
                warnings.append('Missing weight data')
            
            if line.container_type_id and not getattr(line.product_packaging_id, 'volume', 0.0):
                warnings.append('Missing volume data')
            
            line.container_calculation_warning = '; '.join(warnings) if warnings else False
    
    # =========================================================================
    # ONCHANGE METHODS
    # =========================================================================
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Reset packaging when product changes"""
        if self.product_id:
            self.product_packaging_id = False
    
    @api.onchange('entry_mode')
    def _onchange_entry_mode(self):
        """Reset appropriate field when mode changes"""
        if self.entry_mode == 'pkg':
            self.weight = 0.0
        else:
            self.quantity_packaging = 0.0
    
    @api.onchange('weight')
    def _onchange_weight(self):
        """Calculate packages from weight (kg mode only)"""
        if self.entry_mode != 'kg' or not self.weight:
            return
        
        package_weight = self._get_package_weight()
        
        if not package_weight:
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
    
    @api.onchange('quick_production_date', 'product_id')
    def _onchange_quick_production_date(self):
        """Auto-calculate expiry date for quick entry"""
        if self.quick_production_date and self.product_id and not self.quick_expiry_date:
            product_tmpl = self.product_id.product_tmpl_id
            if hasattr(product_tmpl, 'production_to_expiry_days') and product_tmpl.production_to_expiry_days:
                self.quick_expiry_date = self.quick_production_date + timedelta(
                    days=product_tmpl.production_to_expiry_days
                )
    
    @api.onchange('quantity_loaded')
    def _onchange_quantity_loaded_copy_to_produced(self):
        """Auto-copy quantity_loaded to quantity_produced if produced is empty"""
        if self.quantity_loaded and not self.quantity_produced:
            self.quantity_produced = self.quantity_loaded
    
    @api.onchange('quantity_packaging')
    def _onchange_quantity_packaging(self):
        """When quantity changes, check for quantity-based vendor pricing tiers"""
        if not self.quantity_packaging or not self.deal_id.supplier_id:
            return
        
        # Re-fetch supplier price (might hit different quantity tier)
        if self.product_id and self.product_packaging_id:
            self._fetch_supplier_price()
    
    def _get_package_weight(self):
        """Get weight of a single package using priority chain"""
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
        
        return 0.0
    
    # =========================================================================
    # LOT MANAGEMENT ACTIONS
    # =========================================================================
    
    def action_manage_lots(self):
        """Open lot management wizard for multi-lot entry"""
        self.ensure_one()
        
        return {
            'name': _('Manage Lots: %s') % self.product_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal.line.lot.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_deal_line_id': self.id,
                'default_quantity_target': self.quantity_loaded or self.quantity_packaging,
            }
        }
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    @api.constrains('quantity_packaging')
    def _check_quantity(self):
        """Validate quantity is positive"""
        for line in self:
            if line.quantity_packaging <= 0:
                raise ValidationError(_("Quantity must be greater than zero"))
    
    @api.constrains('quantity_loaded', 'lot_ids')
    def _check_quantity_lot_consistency(self):
        """Ensure quantity_loaded matches total lot quantity when lots exist"""
        for line in self:
            if not line.quantity_loaded or not line.lot_ids:
                continue
            
            total_lotted = sum(line.lot_ids.mapped('quantity'))
            if abs(total_lotted - line.quantity_loaded) > 0.001:
                raise ValidationError(_(
                    'Line %s: Total lot quantity (%.2f) must equal loaded quantity (%.2f)'
                ) % (line.product_id.name, total_lotted, line.quantity_loaded))