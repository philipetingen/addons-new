# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealLineProduct(models.Model):
    """Deal Line - Product Selection Extension"""
    _inherit = 'dm.deal.line'
    _description = 'Deal Line - Product Extension'
    
    @api.depends('quantity_packaging', 'quantity_produced')
    def _compute_production_status(self):
        """Compute production completion status"""
        for line in self:
            if not line.quantity_produced or line.quantity_produced == 0:
                line.production_status = 'not_started'
            elif line.quantity_produced < line.quantity_packaging:
                line.production_status = 'partial'
            else:
                line.production_status = 'complete'
    
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