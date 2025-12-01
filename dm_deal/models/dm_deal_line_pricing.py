# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealLinePricing(models.Model):
    """Deal Line - Pricing & Product Selection Extension
    
    Sprint 2: Merged product onchange logic from dm_deal_line_product.py
    """
    _inherit = 'dm.deal.line'
    _description = 'Deal Line - Pricing & Product Extension'
    
    # =========================================================================
    # PRODUCT ONCHANGE HANDLERS (from dm_deal_line_product.py)
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
                
                _logger.info(f"Auto-populated product from customer code: {self.customer_product_code}")
            else:
                return {
                    'warning': {
                        'title': _('Product Code Not Found'),
                        'message': _(
                            f"No product found with customer code '{self.customer_product_code}' "
                            f"for customer {self.deal_id.customer_id.name}"
                        )
                    }
                }
        except Exception as e:
            _logger.error(f"Error looking up customer product code: {str(e)}", exc_info=True)
    
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
        if not self.product_packaging_id or not self.product_id:
            return
        
        # Fetch customer price
        if self.deal_id.customer_id:
            self._fetch_customer_price()
        
        # Fetch supplier price (this also sets line.supplier_id!)
        self._fetch_supplier_price()
        
        # Validate supplier consistency for Line 2+
        if self.deal_id.supplier_id and self.supplier_id:
            if self.deal_id.supplier_id != self.supplier_id:
                raise UserError(
                    f"Cannot add this product!\n\n"
                    f"Deal supplier: {self.deal_id.supplier_id.name}\n"
                    f"Product supplier: {self.supplier_id.name}\n\n"
                    f"Cannot mix suppliers in one deal."
                )
        
        # Trigger template application for Line 1
        if self.deal_id and not self.deal_id.template_id and not self.deal_id.template_selection_pending:
            result = self.deal_id._apply_template_from_lines()
            if result:
                return result
    
    # =========================================================================
    # PRICE COMPUTATION METHODS
    # =========================================================================
    
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
    
    # =========================================================================
    # PRICE FETCHING METHODS
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
        if not self.product_id or not self.product_packaging_id:
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
                raise UserError(
                    f"No vendor pricing found for product '{self.product_id.name}'.\n\n"
                    f"Please configure vendor pricing in the product's Purchase tab."
                )
            
            unique_suppliers = supplier_infos.mapped('partner_id')
            
            # PRIORITY 1: Filter by deal's supplier if set (Line 2+)
            if self.deal_id.supplier_id:
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
                supplier_infos = supplier_infos.filtered(
                    lambda si: si.partner_id == self.supplier_id
                )
                if not supplier_infos:
                    supplier_infos = self.env['product.supplierinfo'].search([
                        '|',
                            ('product_id', '=', self.product_id.id),
                            '&',
                                ('product_id', '=', False),
                                ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
                    ], order='sequence, min_qty, price')
            
            # Find exact package match
            best_info = None
            
            for info in supplier_infos:
                if info.dm_is_package_price and info.dm_packaging_id == self.product_packaging_id:
                    best_info = info
                    break
            
            if not best_info:
                # No exact match - check what's available
                package_infos = supplier_infos.filtered(lambda si: si.dm_is_package_price)
                
                if package_infos:
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
            
            if not best_info:
                raise UserError(f"No vendor pricing found")
            
            # SET SUPPLIER ON LINE
            if not self.supplier_id:
                self.supplier_id = best_info.partner_id
            
            # GET PRICE
            if best_info.dm_is_package_price and best_info.dm_package_price:
                # Use package-based price
                self.price_packaging_purchase = best_info.dm_package_price
            elif best_info.price and self.product_packaging_id.qty:
                # Calculate from unit price
                self.price_packaging_purchase = best_info.price * self.product_packaging_id.qty
            else:
                self.price_packaging_purchase = 0
        
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Error fetching supplier price: {str(e)}", exc_info=True)
            raise UserError(f"Error fetching supplier price: {str(e)}")
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    @api.constrains('price_packaging_sale', 'price_packaging_purchase')
    def _check_prices(self):
        """Validate prices are not negative"""
        for line in self:
            if line.price_packaging_sale < 0:
                raise ValidationError(_("Sale price cannot be negative"))
            if line.price_packaging_purchase < 0:
                raise ValidationError(_("Purchase price cannot be negative"))
                
    @api.model
    def fetch_customer_price_for_wizard(self, customer_id, product_id, packaging_id):
        """
        Static helper for wizards to fetch customer price.
        Returns dict with price data or None.
        """
        if not customer_id or not product_id or not packaging_id:
            return None
        
        try:
            pricelist_item = self.env['dm.customer.pricelist'].search([
                ('partner_id', '=', customer_id),
                ('product_id', '=', product_id),
                ('product_packaging_id', '=', packaging_id),
                ('active', '=', True),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ], limit=1)
            
            if pricelist_item:
                return {
                    'package_price': pricelist_item.package_price,
                    'moq_packages': pricelist_item.moq_packages,
                    'customer_product_code': pricelist_item.customer_product_code,
                    'customer_product_description': pricelist_item.customer_product_description,
                    'currency_id': pricelist_item.currency_id.id if pricelist_item.currency_id else False,
                }
            
            return None
        
        except Exception as e:
            _logger.error(f"Error fetching customer price: {str(e)}", exc_info=True)
            return None
    
    @api.model
    def lookup_product_by_customer_code(self, customer_id, customer_code):
        """
        Static helper to lookup product by customer code.
        Returns dict with product data or None.
        """
        if not customer_id or not customer_code:
            return None
        
        try:
            pricelist_item = self.env['dm.customer.pricelist'].search([
                ('partner_id', '=', customer_id),
                ('customer_product_code', '=', customer_code),
                ('active', '=', True),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ], limit=1)
            
            if pricelist_item:
                return {
                    'product_id': pricelist_item.product_id.id,
                    'product_packaging_id': pricelist_item.product_packaging_id.id,
                    'package_price': pricelist_item.package_price,
                    'moq_packages': pricelist_item.moq_packages,
                    'customer_product_description': pricelist_item.customer_product_description,
                }
            
            return None
        
        except Exception as e:
            _logger.error(f"Error looking up customer product code: {str(e)}", exc_info=True)
            return None                